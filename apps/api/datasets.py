from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Iterator

import duckdb
import pandas as pd
from fastapi import UploadFile

from .schema_inference import (
    apply_overlay_to_dataframe,
    build_column_samples,
    infer_schema,
    save_schema_overlay,
    should_run_inference,
)

logger = logging.getLogger("smarthrbi.datasets")

ALLOWED_EXTENSIONS = {".xlsx"}
MAX_FILES_PER_BATCH = 20
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

CANONICAL_COLUMN_ALIASES = {
    "employee_id": "employee_id",
    "employee id": "employee_id",
    "emp id": "employee_id",
    "员工编号": "employee_id",
    "员工id": "employee_id",
    "employee_name": "employee_name",
    "employee name": "employee_name",
    "name": "employee_name",
    "姓名": "employee_name",
    "department": "department",
    "dept": "department",
    "部门": "department",
    "salary": "salary",
    "compensation": "salary",
    "薪资": "salary",
    "hire_date": "hire_date",
    "hire date": "hire_date",
    "joining date": "hire_date",
    "入职日期": "hire_date",
    "status": "status",
    "state": "status",
    "employee_status": "status",
    "attrition_date": "attrition_date",
    "leave date": "attrition_date",
    "离职日期": "attrition_date",
    "project": "project",
    "manager": "manager",
    "city": "city",
    "region": "region",
    "score": "score",
}


def _normalize_alias_key(raw: str) -> str:
    lowered = raw.strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    ascii_key = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if ascii_key:
        return ascii_key
    return lowered


COLUMN_ALIASES = {_normalize_alias_key(key): value for key, value in CANONICAL_COLUMN_ALIASES.items()}
KNOWN_COLUMNS = set(COLUMN_ALIASES.values())
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(slots=True)
class ParsedUploadFile:
    filename: str
    storage_path: Path
    size_bytes: int
    dataframe: pd.DataFrame
    row_count: int
    column_mapping: dict[str, str]
    normalized_columns: list[str]
    unrecognized_columns: list[str]
    inferred_types: dict[str, str]


class DatasetUploadError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        reasons: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.reasons = reasons or []

    def to_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.reasons:
            detail["reasons"] = self.reasons
        return detail


class DuckDBSessionManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, Lock] = {}
        self._lock_guard = Lock()

    def session_id(self, user_id: str, project_id: str) -> str:
        normalized_user = _sanitize_slug(user_id)
        normalized_project = _sanitize_slug(project_id)
        digest = hashlib.sha1(f"{user_id}::{project_id}".encode("utf-8")).hexdigest()[:12]
        return f"{normalized_user}__{normalized_project}__{digest}"

    def db_path(self, user_id: str, project_id: str) -> Path:
        return self.base_dir / f"{self.session_id(user_id, project_id)}.duckdb"

    def recycle_sessions(self, max_idle_hours: int = 24) -> list[str]:
        now = time.time()
        ttl_seconds = max_idle_hours * 3600
        removed: list[str] = []
        for db_file in self.base_dir.glob("*.duckdb"):
            if now - db_file.stat().st_mtime > ttl_seconds:
                db_file.unlink(missing_ok=True)
                removed.append(db_file.name)
        return removed

    @contextmanager
    def connection(self, user_id: str, project_id: str) -> Iterator[duckdb.DuckDBPyConnection]:
        session_id = self.session_id(user_id, project_id)
        with self._get_lock(session_id):
            db_path = self.db_path(user_id, project_id)
            conn = duckdb.connect(str(db_path))
            try:
                yield conn
            finally:
                conn.close()

    def _get_lock(self, session_id: str) -> Lock:
        with self._lock_guard:
            if session_id not in self._locks:
                self._locks[session_id] = Lock()
            return self._locks[session_id]


class DatasetStorage:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.raw_dir = root_dir / "raw"
        self.meta_dir = root_dir / "metadata"
        self.events_file = root_dir / "upload_events.log"

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_file(self, batch_id: str, filename: str, content: bytes) -> Path:
        batch_dir = self.raw_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _sanitize_filename(filename)
        target = batch_dir / safe_name
        target.write_bytes(content)
        return target

    def save_metadata(self, batch_id: str, payload: dict[str, Any]) -> None:
        target = self.meta_dir / f"{batch_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_metadata(self, batch_id: str) -> dict[str, Any]:
        target = self.meta_dir / f"{batch_id}.json"
        if not target.exists():
            raise DatasetUploadError(
                code="BATCH_NOT_FOUND",
                message=f"Batch {batch_id} not found",
                status_code=404,
            )
        return json.loads(target.read_text(encoding="utf-8"))

    def append_event(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self.events_file.open("a", encoding="utf-8") as fp:
            fp.write(f"{line}\n")


class DatasetIngestionService:
    def __init__(
        self,
        upload_root: Path,
        *,
        ai_api_key: str = "",
        ai_model: str = "claude-haiku-4-5-20251001",
        ai_timeout: float = 30.0,
    ) -> None:
        self.upload_root = upload_root
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.storage = DatasetStorage(upload_root)
        self.session_manager = DuckDBSessionManager(upload_root / "duckdb")
        self._ai_api_key = ai_api_key
        self._ai_model = ai_model
        self._ai_timeout = ai_timeout

    async def upload_files(
        self,
        *,
        user_id: str,
        project_id: str,
        files: list[UploadFile],
    ) -> dict[str, Any]:
        if not files:
            raise DatasetUploadError(
                code="NO_FILES",
                message="At least one Excel file is required",
            )
        if len(files) > MAX_FILES_PER_BATCH:
            raise DatasetUploadError(
                code="TOO_MANY_FILES",
                message=f"A batch accepts at most {MAX_FILES_PER_BATCH} files",
                reasons=[f"received={len(files)}"],
            )

        batch_id = uuid.uuid4().hex
        started = time.perf_counter()
        parsed_files: list[ParsedUploadFile] = []

        try:
            for upload in files:
                parsed = await self._parse_file(batch_id=batch_id, upload=upload)
                parsed_files.append(parsed)

            merged_df, diagnostics = self._merge_files(parsed_files)

            # --- LLM schema inference on the final merged DataFrame ---
            # Run after merge so the overlay covers all columns from all files.
            total_cols = len(merged_df.columns)
            all_unrecognized = list({c for f in parsed_files for c in f.unrecognized_columns})
            if self._ai_api_key and should_run_inference(all_unrecognized, total_cols):
                logger.info(
                    "schema_inference_triggered batch_id=%s unrecognized=%d total=%d",
                    batch_id,
                    len(all_unrecognized),
                    total_cols,
                )
                # Sample values from merged df using original-column names that survived
                column_samples = build_column_samples(merged_df)
                overlay = infer_schema(
                    column_samples=column_samples,
                    ai_api_key=self._ai_api_key,
                    ai_model=self._ai_model,
                    timeout=self._ai_timeout,
                )
                if overlay.get("columns"):
                    merged_df = apply_overlay_to_dataframe(merged_df, overlay)
                    # Rebuild each ParsedUploadFile's metadata to reflect renamed columns
                    known = set(COLUMN_ALIASES.values())
                    for item in parsed_files:
                        new_cols = [
                            overlay.get("columns", {}).get(c, {}).get("canonical", c)
                            if isinstance(overlay.get("columns", {}).get(c), dict) else c
                            for c in item.normalized_columns
                        ]
                        item.normalized_columns = new_cols
                        item.unrecognized_columns = [c for c in new_cols if c not in known and c != "source_file"]
                    save_schema_overlay(
                        meta_dir=self.storage.meta_dir,
                        batch_id=batch_id,
                        overlay=overlay,
                        column_mapping={c: merged_df.columns[i] for i, c in enumerate(merged_df.columns)},
                    )
            # --- end inference ---

            quality_report = self._build_quality_report(
                batch_id=batch_id,
                parsed_files=parsed_files,
                merged_df=merged_df,
            )

            session_id = self.session_manager.session_id(user_id, project_id)
            dataset_table = f"dataset_{batch_id}"
            with self.session_manager.connection(user_id, project_id) as conn:
                conn.register("upload_df", merged_df)
                conn.execute(f'CREATE OR REPLACE TABLE "{dataset_table}" AS SELECT * FROM upload_df')
                conn.unregister("upload_df")

            duration_ms = int((time.perf_counter() - started) * 1000)
            metadata = {
                "batch_id": batch_id,
                "user_id": user_id,
                "project_id": project_id,
                "session_id": session_id,
                "dataset_table": dataset_table,
                "created_at": _utc_now(),
                "duration_ms": duration_ms,
                "files": [
                    {
                        "file_name": item.filename,
                        "storage_path": str(item.storage_path),
                        "size_bytes": item.size_bytes,
                        "row_count": item.row_count,
                        "columns": item.normalized_columns,
                        "column_mapping": item.column_mapping,
                        "unrecognized_columns": item.unrecognized_columns,
                    }
                    for item in parsed_files
                ],
                "diagnostics": diagnostics,
                "quality_report": quality_report,
            }
            self.storage.save_metadata(batch_id, metadata)
            self.storage.append_event(
                {
                    "timestamp": _utc_now(),
                    "status": "success",
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "project_id": project_id,
                    "duration_ms": duration_ms,
                    "file_count": len(files),
                }
            )
            logger.info(
                "upload_succeeded batch_id=%s user_id=%s project_id=%s duration_ms=%d",
                batch_id,
                user_id,
                project_id,
                duration_ms,
            )

            return {
                "batch_id": batch_id,
                "session_id": session_id,
                "dataset_table": dataset_table,
                "file_count": len(files),
                "duration_ms": duration_ms,
                "diagnostics": diagnostics,
            }
        except DatasetUploadError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.storage.append_event(
                {
                    "timestamp": _utc_now(),
                    "status": "failed",
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "project_id": project_id,
                    "duration_ms": duration_ms,
                    "reason": exc.to_detail(),
                }
            )
            logger.warning(
                "upload_failed batch_id=%s user_id=%s project_id=%s reason=%s",
                batch_id,
                user_id,
                project_id,
                exc.code,
            )
            raise

    def get_quality_report(self, batch_id: str) -> dict[str, Any]:
        metadata = self.storage.load_metadata(batch_id)
        return metadata["quality_report"]

    def list_tables(self, *, user_id: str, project_id: str) -> list[str]:
        with self.session_manager.connection(user_id, project_id) as conn:
            rows = conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
            ).fetchall()
        return [row[0] for row in rows]

    def get_row_count(self, *, user_id: str, project_id: str, table_name: str) -> int:
        safe_table = _safe_identifier(table_name)
        with self.session_manager.connection(user_id, project_id) as conn:
            row = conn.execute(f'SELECT COUNT(*) FROM "{safe_table}"').fetchone()
        return int(row[0])

    async def _parse_file(self, *, batch_id: str, upload: UploadFile) -> ParsedUploadFile:
        filename = upload.filename or "uploaded.xlsx"
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise DatasetUploadError(
                code="UNSUPPORTED_FILE_TYPE",
                message=f"Unsupported file type: {extension or 'unknown'}",
                reasons=[f"file={filename}", f"allowed={','.join(sorted(ALLOWED_EXTENSIONS))}"],
            )

        content = await upload.read()
        size_bytes = len(content)
        if size_bytes == 0:
            raise DatasetUploadError(
                code="EMPTY_FILE",
                message=f"File is empty: {filename}",
                reasons=[f"file={filename}"],
            )
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise DatasetUploadError(
                code="FILE_TOO_LARGE",
                message=f"File exceeds size limit ({MAX_FILE_SIZE_BYTES} bytes): {filename}",
                reasons=[f"file={filename}", f"size_bytes={size_bytes}"],
            )

        storage_path = self.storage.save_raw_file(batch_id, filename, content)
        dataframe = self._read_excel(storage_path, filename=filename)

        normalized_df, mapping, unrecognized = _normalize_dataframe(dataframe)

        inferred_types = {
            column: _infer_series_type(normalized_df[column])
            for column in normalized_df.columns
            if column != "source_file"
        }
        normalized_df["source_file"] = filename

        return ParsedUploadFile(
            filename=filename,
            storage_path=storage_path,
            size_bytes=size_bytes,
            dataframe=normalized_df,
            row_count=int(len(normalized_df)),
            column_mapping=mapping,
            normalized_columns=list(normalized_df.columns),
            unrecognized_columns=unrecognized,
            inferred_types=inferred_types,
        )

    def _read_excel(self, path: Path, *, filename: str) -> pd.DataFrame:
        try:
            dataframe = pd.read_excel(path, dtype=object)
        except Exception as exc:  # pragma: no cover - defensive; covered via API test
            raise DatasetUploadError(
                code="INVALID_EXCEL_FILE",
                message=f"Unable to parse Excel file: {filename}",
                reasons=[str(exc)],
            ) from exc

        if dataframe.empty and len(dataframe.columns) == 0:
            raise DatasetUploadError(
                code="EMPTY_SHEET",
                message=f"Excel file has no usable sheet data: {filename}",
            )
        return dataframe

    def _merge_files(self, files: list[ParsedUploadFile]) -> tuple[pd.DataFrame, dict[str, Any]]:
        all_columns = []
        seen = set()
        for item in files:
            for column in item.dataframe.columns:
                if column not in seen:
                    seen.add(column)
                    all_columns.append(column)

        aligned_frames: list[pd.DataFrame] = []
        for item in files:
            frame = item.dataframe.copy()
            missing_columns = [col for col in all_columns if col not in frame.columns]
            for column in missing_columns:
                frame[column] = pd.NA
            aligned_frames.append(frame[all_columns])

        merged = pd.concat(aligned_frames, ignore_index=True)
        diagnostics = {
            "union_mode": "union_by_name",
            "source_file_count": len(files),
            "result_row_count": int(len(merged)),
            "result_column_count": int(len(merged.columns)),
            "unrecognized_columns": [
                {
                    "file_name": item.filename,
                    "columns": item.unrecognized_columns,
                }
                for item in files
                if item.unrecognized_columns
            ],
        }
        return merged, diagnostics

    def _build_quality_report(
        self,
        *,
        batch_id: str,
        parsed_files: list[ParsedUploadFile],
        merged_df: pd.DataFrame,
    ) -> dict[str, Any]:
        blocking_issues: list[dict[str, Any]] = []
        file_reports: list[dict[str, Any]] = []

        for item in parsed_files:
            null_rates = {
                column: _round_float(float(item.dataframe[column].isna().mean()))
                for column in item.dataframe.columns
                if column != "source_file"
            }
            file_reports.append(
                {
                    "file_name": item.filename,
                    "row_count": item.row_count,
                    "column_count": len(item.dataframe.columns),
                    "null_rates": null_rates,
                    "column_types": item.inferred_types,
                    "unrecognized_columns": item.unrecognized_columns,
                }
            )

        column_reports: list[dict[str, Any]] = []
        for column in merged_df.columns:
            if column == "source_file":
                continue

            series = merged_df[column]
            non_null = series.dropna()
            null_rate = float(series.isna().mean())
            duplicate_rate = float(non_null.duplicated().mean()) if not non_null.empty else 0.0

            types_by_file: dict[str, str] = {}
            for item in parsed_files:
                if column in item.dataframe.columns:
                    types_by_file[item.filename] = item.inferred_types.get(column, "null")

            distinct_types = {value for value in types_by_file.values() if value != "null"}
            type_drift = len(distinct_types) > 1

            if type_drift:
                blocking_issues.append(
                    {
                        "severity": "high",
                        "rule": "type_drift",
                        "column": column,
                        "description": f"Column {column} has inconsistent inferred types across files",
                    }
                )
            if null_rate >= 0.95:
                blocking_issues.append(
                    {
                        "severity": "medium",
                        "rule": "high_null_rate",
                        "column": column,
                        "description": f"Column {column} null rate is {null_rate:.2%}",
                    }
                )

            involved_files = [item.filename for item in parsed_files if column in item.dataframe.columns]
            column_reports.append(
                {
                    "column": column,
                    "null_rate": _round_float(null_rate),
                    "duplicate_rate": _round_float(duplicate_rate),
                    "type_drift": type_drift,
                    "types_by_file": types_by_file,
                    "files": involved_files,
                }
            )

        return {
            "batch_id": batch_id,
            "generated_at": _utc_now(),
            "summary": {
                "file_count": len(parsed_files),
                "row_count": int(len(merged_df)),
                "column_count": int(len(merged_df.columns)),
            },
            "files": file_reports,
            "columns": column_reports,
            "blocking_issues": blocking_issues,
            "can_publish_to_semantic_layer": len(
                [issue for issue in blocking_issues if issue["severity"] == "high"]
            )
            == 0,
        }


def _round_float(value: float) -> float:
    return round(value, 6)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_slug(raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", raw.strip()).strip("_")
    return slug or "unknown"


def _sanitize_filename(raw: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    return safe_name or "uploaded.xlsx"


def _safe_identifier(name: str) -> str:
    if not SAFE_IDENTIFIER_RE.match(name):
        raise DatasetUploadError(
            code="INVALID_IDENTIFIER",
            message=f"Invalid identifier: {name}",
            status_code=400,
        )
    return name


def _normalize_column_name(raw: str) -> str:
    key = _normalize_alias_key(raw)
    if key in COLUMN_ALIASES:
        return COLUMN_ALIASES[key]
    if re.match(r"^[a-z0-9_]+$", key):
        return key
    fallback = re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_")
    return fallback.lower() or "column"


def _normalize_dataframe(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    unrecognized: list[str] = []
    used: set[str] = set()

    for column in dataframe.columns:
        original = str(column)
        normalized = _normalize_column_name(original)
        base = normalized
        suffix = 1
        while normalized in used:
            suffix += 1
            normalized = f"{base}_{suffix}"
        used.add(normalized)
        mapping[original] = normalized

        if base not in KNOWN_COLUMNS and normalized != "source_file":
            unrecognized.append(normalized)

    normalized_df = dataframe.rename(columns=mapping)
    return normalized_df, mapping, sorted(set(unrecognized))


def _infer_series_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "null"

    as_text = non_null.astype(str).str.strip()
    lowered = as_text.str.lower()
    if lowered.isin({"true", "false", "yes", "no", "0", "1"}).all():
        return "boolean"

    numeric = pd.to_numeric(as_text, errors="coerce")
    if numeric.notna().all():
        return "number"

    datetimes = pd.to_datetime(as_text, errors="coerce", format="mixed")
    if datetimes.notna().all():
        return "datetime"

    return "string"


@lru_cache(maxsize=8)
def _service_cache(upload_root: str, ai_api_key: str, ai_model: str, ai_timeout: float) -> DatasetIngestionService:
    return DatasetIngestionService(
        Path(upload_root),
        ai_api_key=ai_api_key,
        ai_model=ai_model,
        ai_timeout=ai_timeout,
    )


def get_dataset_service(upload_root: Path, *, ai_api_key: str = "", ai_model: str = "claude-haiku-4-5-20251001", ai_timeout: float = 30.0) -> DatasetIngestionService:
    return _service_cache(str(upload_root.resolve()), ai_api_key, ai_model, ai_timeout)


def clear_dataset_service_cache() -> None:
    _service_cache.cache_clear()
