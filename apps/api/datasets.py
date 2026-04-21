from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Iterator

import duckdb

SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DatasetAccessError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class DuckDBSessionManager:
    """Read/query access for DuckDB datasets.

    Excel ingestion no longer happens here. User-uploaded workbooks are written
    only by the agentic ingestion runtime into workspace-scoped DuckDB files.
    The legacy user/project path is kept as a read compatibility path for older
    saved views and tests that seed DuckDB directly.
    """

    def __init__(self, upload_root: Path) -> None:
        self.upload_root = upload_root
        self.legacy_base_dir = upload_root / "duckdb"
        self.workspace_base_dir = upload_root / "agentic_ingestion" / "duckdb"
        self.legacy_base_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, Lock] = {}
        self._lock_guard = Lock()

    def session_id(self, user_id: str, project_id: str) -> str:
        normalized_user = _sanitize_slug(user_id)
        normalized_project = _sanitize_slug(project_id)
        digest = hashlib.sha1(f"{user_id}::{project_id}".encode("utf-8")).hexdigest()[:12]
        return f"{normalized_user}__{normalized_project}__{digest}"

    def db_path(self, user_id: str, project_id: str) -> Path:
        return self.legacy_base_dir / f"{self.session_id(user_id, project_id)}.duckdb"

    def workspace_db_path(self, workspace_id: str) -> Path:
        safe_workspace = _sanitize_slug(workspace_id) or "workspace"
        return (self.workspace_base_dir / f"{safe_workspace}.duckdb").resolve()

    @contextmanager
    def connection(
        self,
        user_id: str,
        project_id: str,
        *,
        workspace_id: str | None = None,
    ) -> Iterator[duckdb.DuckDBPyConnection]:
        if workspace_id and workspace_id.strip():
            lock_key = f"workspace::{workspace_id.strip()}"
            db_path = self.workspace_db_path(workspace_id)
        else:
            lock_key = f"legacy::{self.session_id(user_id, project_id)}"
            db_path = self.db_path(user_id, project_id)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_lock(lock_key):
            conn = duckdb.connect(str(db_path))
            try:
                yield conn
            finally:
                conn.close()

    def _get_lock(self, key: str) -> Lock:
        with self._lock_guard:
            if key not in self._locks:
                self._locks[key] = Lock()
            return self._locks[key]


class DatasetQueryService:
    def __init__(self, upload_root: Path) -> None:
        self.upload_root = upload_root
        self.session_manager = DuckDBSessionManager(upload_root)

    def list_tables(
        self,
        *,
        user_id: str,
        project_id: str,
        workspace_id: str | None = None,
    ) -> list[str]:
        with self.session_manager.connection(
            user_id,
            project_id,
            workspace_id=workspace_id,
        ) as conn:
            rows = conn.execute("SHOW TABLES").fetchall()
        return sorted(str(row[0]) for row in rows)

    def get_row_count(
        self,
        *,
        user_id: str,
        project_id: str,
        table_name: str,
        workspace_id: str | None = None,
    ) -> int:
        safe_table = _safe_identifier(table_name)
        with self.session_manager.connection(
            user_id,
            project_id,
            workspace_id=workspace_id,
        ) as conn:
            row = conn.execute(f'SELECT COUNT(*) FROM "{safe_table}"').fetchone()
        return int(row[0])


def _sanitize_slug(raw: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", raw.strip()).strip("_")
    return slug or "unknown"


def _safe_identifier(name: str) -> str:
    if not SAFE_IDENTIFIER_RE.match(name):
        raise DatasetAccessError(
            code="INVALID_IDENTIFIER",
            message=f"Invalid identifier: {name}",
            status_code=400,
        )
    return name


@lru_cache(maxsize=8)
def _service_cache(upload_root: str) -> DatasetQueryService:
    return DatasetQueryService(Path(upload_root))


def get_dataset_service(
    upload_root: Path,
    *,
    ai_api_key: str = "",
    ai_model: str = "",
    ai_base_url: str = "",
    ai_timeout: float = 0,
) -> DatasetQueryService:
    _ = (ai_api_key, ai_model, ai_base_url, ai_timeout)
    return _service_cache(str(upload_root.resolve()))


def clear_dataset_service_cache() -> None:
    _service_cache.cache_clear()
