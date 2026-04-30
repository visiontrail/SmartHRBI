from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field, field_validator

from .config import get_settings
from .data_policy import forbidden_sensitive_columns, redact_rows

SQLITE_RELATIVE_BASE = Path(__file__).resolve().parent
PUBLISHED_SCHEMA_PATH = SQLITE_RELATIVE_BASE / "migrations" / "0004_published_pages_init.sql"


class PublishedPageError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_detail(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


class PublishedChartSnapshot(BaseModel):
    chart_id: str = Field(min_length=1)
    spec: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    title: str | None = None
    chart_type: str | None = None

    @field_validator("chart_id")
    @classmethod
    def validate_chart_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("chart_id is required")
        return normalized


VISIBILITY_MODES = {"private", "registered", "allowlist"}


class PublishWorkspaceRequest(BaseModel):
    layout: dict[str, Any] = Field(default_factory=dict)
    sidebar: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[PublishedChartSnapshot] = Field(default_factory=list)
    visibility_mode: str = Field(default="private")
    visibility_user_ids: list[str] = Field(default_factory=list)

    @field_validator("visibility_mode")
    @classmethod
    def validate_visibility_mode(cls, value: str) -> str:
        if value not in VISIBILITY_MODES:
            raise ValueError(f"visibility_mode must be one of {VISIBILITY_MODES}")
        return value


class PublishedPage(BaseModel):
    id: str
    workspace_id: str
    version: int
    published_at: str
    published_by: str
    manifest_path: str
    visibility_mode: str = "private"
    visibility_user_ids: list[str] = Field(default_factory=list)

    def to_history_item(self) -> dict[str, Any]:
        user_count = len(self.visibility_user_ids) if self.visibility_mode == "allowlist" else None
        return {
            "page_id": self.id,
            "version": self.version,
            "published_at": self.published_at,
            "published_by": self.published_by,
            "manifest_path": self.manifest_path,
            "visibility_mode": self.visibility_mode,
            "visibility_user_count": user_count,
            "visibility_user_ids": self.visibility_user_ids if self.visibility_mode == "allowlist" else [],
        }

    def is_visible_to(self, *, user_id: str, workspace_member_roles: set[str]) -> bool:
        if self.visibility_mode == "registered":
            return True
        if self.visibility_mode == "private":
            return bool(workspace_member_roles & {"owner", "editor"})
        if self.visibility_mode == "allowlist":
            if bool(workspace_member_roles & {"owner", "editor"}):
                return True
            if user_id and any(uid == user_id for uid in self.visibility_user_ids):
                return True
            return False
        return False


@dataclass(slots=True)
class SnapshotWriteResult:
    manifest_path: Path
    manifest: dict[str, Any]


class SnapshotWriter:
    def __init__(self, *, upload_dir: Path, max_rows: int) -> None:
        self.upload_dir = upload_dir
        self.max_rows = max_rows

    def write(
        self,
        *,
        workspace_id: str,
        version: int,
        layout: dict[str, Any],
        sidebar: list[dict[str, Any]],
        charts: list[PublishedChartSnapshot],
        actor_role: str,
        published_at: str,
    ) -> SnapshotWriteResult:
        normalized_workspace_id = workspace_id.strip()
        if not normalized_workspace_id:
            raise PublishedPageError(
                code="WORKSPACE_ID_REQUIRED",
                message="workspace_id is required",
                status_code=422,
            )

        target_dir = self.upload_dir / "published" / _safe_path_segment(normalized_workspace_id) / str(version)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        charts_dir = target_dir / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)

        chart_entries: list[dict[str, Any]] = []
        for chart in charts:
            chart_dir = charts_dir / _safe_path_segment(chart.chart_id)
            chart_dir.mkdir(parents=True, exist_ok=True)

            rows = list(chart.rows)
            capped_rows = rows[: self.max_rows]
            data_truncated = len(rows) > self.max_rows
            safe_rows = self._sanitize_rows(capped_rows, role=actor_role)

            spec_payload = dict(chart.spec)
            spec_payload.setdefault("chart_id", chart.chart_id)
            if chart.title:
                spec_payload.setdefault("title", chart.title)
            if chart.chart_type:
                spec_payload.setdefault("chart_type", chart.chart_type)

            spec_path = chart_dir / "spec.json"
            data_path = chart_dir / "data.json"
            _write_json(spec_path, spec_payload)
            _write_json(data_path, safe_rows)

            chart_entries.append(
                {
                    "chart_id": chart.chart_id,
                    "title": chart.title or spec_payload.get("title") or chart.chart_id,
                    "chart_type": chart.chart_type or spec_payload.get("chart_type"),
                    "spec_path": _relative_posix(spec_path, target_dir),
                    "data_path": _relative_posix(data_path, target_dir),
                    "row_count": len(safe_rows),
                    "source_row_count": len(rows),
                    "data_truncated": data_truncated,
                }
            )

        manifest = {
            "workspace_id": normalized_workspace_id,
            "version": version,
            "published_at": published_at,
            "layout": layout,
            "sidebar": sidebar,
            "charts": chart_entries,
        }
        manifest_path = target_dir / "manifest.json"
        _write_json(manifest_path, manifest)
        return SnapshotWriteResult(manifest_path=manifest_path, manifest=manifest)

    def _sanitize_rows(self, rows: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
        blocked = forbidden_sensitive_columns(role)
        filtered_rows: list[dict[str, Any]] = []
        for row in rows:
            filtered_rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if _normalize_identifier(str(key)) not in blocked
                }
            )
        return redact_rows(filtered_rows, role=role)


class PublishedPageStore:
    def __init__(self, *, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_schema()

    def next_version(self, *, workspace_id: str) -> int:
        normalized_workspace_id = workspace_id.strip()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS latest_version FROM published_pages WHERE workspace_id = ?",
                (normalized_workspace_id,),
            ).fetchone()
        return int(row["latest_version"]) + 1 if row is not None else 1

    def create(
        self,
        *,
        workspace_id: str,
        version: int,
        published_by: str,
        manifest_path: Path,
        published_at: str | None = None,
        visibility_mode: str = "private",
        visibility_user_ids: list[str] | None = None,
    ) -> PublishedPage:
        normalized_workspace_id = workspace_id.strip()
        normalized_publisher = published_by.strip()
        if not normalized_workspace_id:
            raise PublishedPageError(
                code="WORKSPACE_ID_REQUIRED",
                message="workspace_id is required",
                status_code=422,
            )
        if not normalized_publisher:
            raise PublishedPageError(
                code="AUTH_REQUIRED",
                message="published_by is required",
                status_code=401,
            )

        page_id = uuid.uuid4().hex
        now = published_at or _utc_now()
        vis_user_ids_json = json.dumps(visibility_user_ids or [])
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO published_pages (
                    id, workspace_id, version, published_at, published_by, manifest_path,
                    visibility_mode, visibility_user_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    normalized_workspace_id,
                    version,
                    now,
                    normalized_publisher,
                    str(manifest_path),
                    visibility_mode,
                    vis_user_ids_json,
                ),
            )
            conn.commit()

        return PublishedPage(
            id=page_id,
            workspace_id=normalized_workspace_id,
            version=version,
            published_at=now,
            published_by=normalized_publisher,
            manifest_path=str(manifest_path),
            visibility_mode=visibility_mode,
            visibility_user_ids=visibility_user_ids or [],
        )

    def get(self, *, page_id: str) -> PublishedPage:
        normalized_page_id = page_id.strip()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, workspace_id, version, published_at, published_by, manifest_path,
                       COALESCE(visibility_mode, 'private') AS visibility_mode,
                       visibility_user_ids
                FROM published_pages
                WHERE id = ?
                """,
                (normalized_page_id,),
            ).fetchone()
        if row is None:
            raise PublishedPageError(
                code="PUBLISHED_PAGE_NOT_FOUND",
                message="Published page not found",
                status_code=404,
            )
        return self._serialize(row)

    def get_latest(self, *, workspace_id: str) -> PublishedPage:
        normalized_workspace_id = workspace_id.strip()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, workspace_id, version, published_at, published_by, manifest_path,
                       COALESCE(visibility_mode, 'private') AS visibility_mode,
                       visibility_user_ids
                FROM published_pages
                WHERE workspace_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (normalized_workspace_id,),
            ).fetchone()
        if row is None:
            raise PublishedPageError(
                code="PUBLISHED_PAGE_NOT_FOUND",
                message="Published page not found",
                status_code=404,
            )
        return self._serialize(row)

    def list_by_workspace(self, *, workspace_id: str) -> list[PublishedPage]:
        normalized_workspace_id = workspace_id.strip()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, version, published_at, published_by, manifest_path,
                       COALESCE(visibility_mode, 'private') AS visibility_mode,
                       visibility_user_ids
                FROM published_pages
                WHERE workspace_id = ?
                ORDER BY version DESC
                """,
                (normalized_workspace_id,),
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def list_latest_by_workspace(self) -> list[PublishedPage]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT pp.id, pp.workspace_id, pp.version, pp.published_at, pp.published_by,
                       pp.manifest_path,
                       COALESCE(pp.visibility_mode, 'private') AS visibility_mode,
                       pp.visibility_user_ids
                FROM published_pages AS pp
                JOIN (
                    SELECT workspace_id, MAX(version) AS version
                    FROM published_pages
                    GROUP BY workspace_id
                ) AS latest
                  ON latest.workspace_id = pp.workspace_id
                 AND latest.version = pp.version
                ORDER BY pp.published_at DESC
                """
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def update_visibility(
        self,
        *,
        page_id: str,
        visibility_mode: str,
        visibility_user_ids: list[str],
    ) -> PublishedPage:
        vis_user_ids_json = json.dumps(visibility_user_ids)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE published_pages
                SET visibility_mode = ?, visibility_user_ids = ?
                WHERE id = ?
                """,
                (visibility_mode, vis_user_ids_json, page_id),
            )
            conn.commit()
        return self.get(page_id=page_id)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(PUBLISHED_SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
            # Add visibility columns (idempotent)
            for stmt in [
                "ALTER TABLE published_pages ADD COLUMN visibility_mode TEXT NOT NULL DEFAULT 'private'",
                "ALTER TABLE published_pages ADD COLUMN visibility_user_ids TEXT",
            ]:
                try:
                    conn.execute(stmt)
                    conn.commit()
                except Exception:
                    pass  # Column already exists

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _serialize(row: sqlite3.Row) -> PublishedPage:
        raw_ids = row["visibility_user_ids"]
        try:
            vis_ids = json.loads(raw_ids) if raw_ids else []
            if not isinstance(vis_ids, list):
                vis_ids = []
        except (json.JSONDecodeError, TypeError):
            vis_ids = []
        return PublishedPage(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            version=int(row["version"]),
            published_at=str(row["published_at"]),
            published_by=str(row["published_by"]),
            manifest_path=str(row["manifest_path"]),
            visibility_mode=str(row["visibility_mode"]) if row["visibility_mode"] else "private",
            visibility_user_ids=[str(x) for x in vis_ids if x is not None],
        )


@lru_cache(maxsize=2)
def _cached_published_page_store(storage_key: str) -> PublishedPageStore:
    parsed = urlparse(storage_key)
    if parsed.scheme == "sqlite":
        db_path = _sqlite_db_path_from_url(storage_key).parent / "published_pages.sqlite3"
    else:
        state_root = Path(storage_key)
        state_root.mkdir(parents=True, exist_ok=True)
        db_path = state_root / "published_pages.sqlite3"
    return PublishedPageStore(db_path=db_path)


def get_published_page_store() -> PublishedPageStore:
    settings = get_settings()
    db_url = settings.database_url.strip()
    if db_url.startswith("sqlite://"):
        storage_key = db_url
    else:
        storage_key = str((settings.upload_dir / "state").resolve())
    return _cached_published_page_store(storage_key)


def clear_published_page_store_cache() -> None:
    _cached_published_page_store.cache_clear()


def get_snapshot_writer() -> SnapshotWriter:
    settings = get_settings()
    return SnapshotWriter(upload_dir=settings.upload_dir, max_rows=settings.agent_max_sql_rows)


def read_manifest(page: PublishedPage) -> dict[str, Any]:
    manifest_path = Path(page.manifest_path)
    if not manifest_path.exists():
        raise PublishedPageError(
            code="PUBLISHED_MANIFEST_NOT_FOUND",
            message="Published manifest not found",
            status_code=404,
        )
    decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise PublishedPageError(
            code="PUBLISHED_MANIFEST_INVALID",
            message="Published manifest is invalid",
            status_code=500,
        )
    return decoded


def read_chart_data(page: PublishedPage, *, chart_id: str) -> dict[str, Any]:
    manifest = read_manifest(page)
    chart_entries = manifest.get("charts")
    if not isinstance(chart_entries, list):
        chart_entries = []
    chart_entry = next(
        (
            item
            for item in chart_entries
            if isinstance(item, dict) and str(item.get("chart_id") or "") == chart_id
        ),
        None,
    )
    if chart_entry is None:
        raise PublishedPageError(
            code="PUBLISHED_CHART_NOT_FOUND",
            message="Published chart not found",
            status_code=404,
        )

    manifest_dir = Path(page.manifest_path).parent
    spec = _read_json_file(manifest_dir / str(chart_entry.get("spec_path") or ""))
    rows = _read_json_file(manifest_dir / str(chart_entry.get("data_path") or ""))
    return {
        "page_id": page.id,
        "chart_id": chart_id,
        "spec": spec if isinstance(spec, dict) else {},
        "rows": rows if isinstance(rows, list) else [],
        "data_truncated": bool(chart_entry.get("data_truncated")),
    }


def _sqlite_db_path_from_url(database_url: str) -> Path:
    parsed = urlparse(database_url)
    raw_path = unquote(parsed.path)
    if raw_path.startswith("//"):
        return Path("/" + raw_path.lstrip("/")).resolve()
    if raw_path.startswith("/"):
        raw_path = raw_path[1:]
    return (SQLITE_RELATIVE_BASE / raw_path).resolve()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _read_json_file(path: Path) -> Any:
    if not path.exists():
        raise PublishedPageError(
            code="PUBLISHED_SNAPSHOT_FILE_NOT_FOUND",
            message="Published snapshot file not found",
            status_code=404,
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_path_segment(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip())
    normalized = normalized.strip(".-")
    return normalized or uuid.uuid4().hex


def _relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _normalize_identifier(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "_", lowered)
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    return re.sub(r"_+", "_", lowered).strip("_")
