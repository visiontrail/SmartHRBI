from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from .agentic_ingestion.schema import initialize_sqlite_schema
from .auth import AuthIdentity, require_permission
from .workspaces import WorkspaceError, get_workspace_service

BUSINESS_TYPES = ("roster", "project_progress", "attendance", "other")
WRITE_MODES = ("update_existing", "time_partitioned_new_table", "new_table", "append_only")
TIME_GRAINS = ("none", "month", "quarter", "year")
TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class TableCatalogError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_detail(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


class TableCatalogEntryCreateRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=128)
    human_label: str = Field(min_length=1, max_length=120)
    business_type: Literal["roster", "project_progress", "attendance", "other"]
    write_mode: Literal[
        "update_existing",
        "time_partitioned_new_table",
        "new_table",
        "append_only",
    ]
    time_grain: Literal["none", "month", "quarter", "year"] = "none"
    primary_keys: list[str] = Field(default_factory=list)
    match_columns: list[str] = Field(default_factory=list)
    is_active_target: bool = True
    description: str = Field(default="", max_length=1000)

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, value: str) -> str:
        normalized = value.strip()
        if not TABLE_NAME_PATTERN.match(normalized):
            raise ValueError("table_name must be a valid SQL identifier")
        return normalized.lower()

    @field_validator("human_label")
    @classmethod
    def validate_human_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("human_label cannot be empty")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("primary_keys", "match_columns")
    @classmethod
    def validate_column_lists(cls, values: list[str]) -> list[str]:
        return _normalize_column_list(values)


class TableCatalogEntryUpdateRequest(BaseModel):
    table_name: str | None = Field(default=None, min_length=1, max_length=128)
    human_label: str | None = Field(default=None, min_length=1, max_length=120)
    business_type: Literal["roster", "project_progress", "attendance", "other"] | None = None
    write_mode: Literal[
        "update_existing",
        "time_partitioned_new_table",
        "new_table",
        "append_only",
    ] | None = None
    time_grain: Literal["none", "month", "quarter", "year"] | None = None
    primary_keys: list[str] | None = None
    match_columns: list[str] | None = None
    is_active_target: bool | None = None
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not TABLE_NAME_PATTERN.match(normalized):
            raise ValueError("table_name must be a valid SQL identifier")
        return normalized.lower()

    @field_validator("human_label")
    @classmethod
    def validate_human_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("human_label cannot be empty")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("primary_keys", "match_columns")
    @classmethod
    def validate_column_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return _normalize_column_list(values)


@dataclass(slots=True)
class TableCatalogService:
    db_path: Path
    _lock: Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize_schema()

    def list_entries(self, *, workspace_id: str) -> list[dict[str, Any]]:
        normalized_workspace_id = workspace_id.strip()
        if not normalized_workspace_id:
            raise TableCatalogError(
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found",
                status_code=404,
            )

        with self._lock, self._connect() as conn:
            self._assert_workspace_exists(conn, workspace_id=normalized_workspace_id)
            rows = conn.execute(
                """
                SELECT *
                FROM table_catalog
                WHERE workspace_id = ?
                ORDER BY business_type ASC, is_active_target DESC, updated_at DESC
                """,
                (normalized_workspace_id,),
            ).fetchall()

        return [self._serialize_entry(row) for row in rows]

    def get_entry(self, *, workspace_id: str, catalog_id: str) -> dict[str, Any]:
        row = self._get_entry_row(workspace_id=workspace_id, catalog_id=catalog_id)
        return self._serialize_entry(row)

    def create_entry(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        payload: TableCatalogEntryCreateRequest,
    ) -> dict[str, Any]:
        normalized_workspace_id = workspace_id.strip()
        normalized_actor = actor_user_id.strip()
        catalog_id = uuid.uuid4().hex
        now = _utc_now()

        with self._lock, self._connect() as conn:
            self._assert_workspace_exists(conn, workspace_id=normalized_workspace_id)
            self._ensure_user_record(conn, user_id=normalized_actor)

            if payload.is_active_target:
                conn.execute(
                    """
                    UPDATE table_catalog
                    SET is_active_target = 0, updated_by = ?, updated_at = ?
                    WHERE workspace_id = ? AND business_type = ?
                    """,
                    (normalized_actor, now, normalized_workspace_id, payload.business_type),
                )

            conn.execute(
                """
                INSERT INTO table_catalog (
                    id,
                    workspace_id,
                    table_name,
                    human_label,
                    business_type,
                    write_mode,
                    time_grain,
                    primary_keys,
                    match_columns,
                    is_active_target,
                    description,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    catalog_id,
                    normalized_workspace_id,
                    payload.table_name,
                    payload.human_label,
                    payload.business_type,
                    payload.write_mode,
                    payload.time_grain,
                    json.dumps(payload.primary_keys, ensure_ascii=False),
                    json.dumps(payload.match_columns, ensure_ascii=False),
                    int(payload.is_active_target),
                    payload.description,
                    normalized_actor,
                    normalized_actor,
                    now,
                    now,
                ),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM table_catalog WHERE id = ? AND workspace_id = ?",
                (catalog_id, normalized_workspace_id),
            ).fetchone()

        if row is None:
            raise TableCatalogError(
                code="CATALOG_ENTRY_NOT_FOUND",
                message="Catalog entry not found",
                status_code=404,
            )

        return self._serialize_entry(row)

    def update_entry(
        self,
        *,
        workspace_id: str,
        catalog_id: str,
        actor_user_id: str,
        payload: TableCatalogEntryUpdateRequest,
    ) -> dict[str, Any]:
        normalized_workspace_id = workspace_id.strip()
        normalized_catalog_id = catalog_id.strip()
        normalized_actor = actor_user_id.strip()
        updates = payload.model_dump(exclude_none=True)

        with self._lock, self._connect() as conn:
            self._assert_workspace_exists(conn, workspace_id=normalized_workspace_id)
            self._ensure_user_record(conn, user_id=normalized_actor)

            current = conn.execute(
                "SELECT * FROM table_catalog WHERE id = ? AND workspace_id = ?",
                (normalized_catalog_id, normalized_workspace_id),
            ).fetchone()
            if current is None:
                raise TableCatalogError(
                    code="CATALOG_ENTRY_NOT_FOUND",
                    message="Catalog entry not found",
                    status_code=404,
                )

            if updates:
                business_type = str(updates.get("business_type") or current["business_type"])
                is_active_target = bool(
                    updates.get("is_active_target", bool(current["is_active_target"]))
                )

                if is_active_target:
                    conn.execute(
                        """
                        UPDATE table_catalog
                        SET is_active_target = 0, updated_by = ?, updated_at = ?
                        WHERE workspace_id = ? AND business_type = ? AND id != ?
                        """,
                        (
                            normalized_actor,
                            _utc_now(),
                            normalized_workspace_id,
                            business_type,
                            normalized_catalog_id,
                        ),
                    )

                assignments: list[str] = []
                values: list[Any] = []
                for field_name in (
                    "table_name",
                    "human_label",
                    "business_type",
                    "write_mode",
                    "time_grain",
                    "description",
                    "is_active_target",
                ):
                    if field_name in updates:
                        assignments.append(f"{field_name} = ?")
                        field_value: Any = updates[field_name]
                        if field_name == "is_active_target":
                            field_value = int(bool(field_value))
                        values.append(field_value)

                if "primary_keys" in updates:
                    assignments.append("primary_keys = ?")
                    values.append(json.dumps(updates["primary_keys"], ensure_ascii=False))

                if "match_columns" in updates:
                    assignments.append("match_columns = ?")
                    values.append(json.dumps(updates["match_columns"], ensure_ascii=False))

                if assignments:
                    assignments.extend(("updated_by = ?", "updated_at = ?"))
                    values.extend((normalized_actor, _utc_now(), normalized_catalog_id, normalized_workspace_id))
                    conn.execute(
                        f"""
                        UPDATE table_catalog
                        SET {", ".join(assignments)}
                        WHERE id = ? AND workspace_id = ?
                        """,
                        tuple(values),
                    )
                    conn.commit()

            row = conn.execute(
                "SELECT * FROM table_catalog WHERE id = ? AND workspace_id = ?",
                (normalized_catalog_id, normalized_workspace_id),
            ).fetchone()

        if row is None:
            raise TableCatalogError(
                code="CATALOG_ENTRY_NOT_FOUND",
                message="Catalog entry not found",
                status_code=404,
            )

        return self._serialize_entry(row)

    def delete_entry(self, *, workspace_id: str, catalog_id: str) -> None:
        normalized_workspace_id = workspace_id.strip()
        normalized_catalog_id = catalog_id.strip()

        with self._lock, self._connect() as conn:
            self._assert_workspace_exists(conn, workspace_id=normalized_workspace_id)
            existing = conn.execute(
                "SELECT id FROM table_catalog WHERE id = ? AND workspace_id = ?",
                (normalized_catalog_id, normalized_workspace_id),
            ).fetchone()
            if existing is None:
                raise TableCatalogError(
                    code="CATALOG_ENTRY_NOT_FOUND",
                    message="Catalog entry not found",
                    status_code=404,
                )

            conn.execute(
                "DELETE FROM table_catalog WHERE id = ? AND workspace_id = ?",
                (normalized_catalog_id, normalized_workspace_id),
            )
            conn.commit()

    def get_active_target(
        self,
        *,
        workspace_id: str,
        business_type: Literal["roster", "project_progress", "attendance", "other"],
    ) -> dict[str, Any] | None:
        normalized_workspace_id = workspace_id.strip()

        with self._lock, self._connect() as conn:
            self._assert_workspace_exists(conn, workspace_id=normalized_workspace_id)
            row = conn.execute(
                """
                SELECT *
                FROM table_catalog
                WHERE workspace_id = ?
                  AND business_type = ?
                  AND is_active_target = 1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (normalized_workspace_id, business_type),
            ).fetchone()

        if row is None:
            return None
        return self._serialize_entry(row)

    def _get_entry_row(self, *, workspace_id: str, catalog_id: str) -> sqlite3.Row:
        normalized_workspace_id = workspace_id.strip()
        normalized_catalog_id = catalog_id.strip()

        with self._lock, self._connect() as conn:
            self._assert_workspace_exists(conn, workspace_id=normalized_workspace_id)
            row = conn.execute(
                "SELECT * FROM table_catalog WHERE id = ? AND workspace_id = ?",
                (normalized_catalog_id, normalized_workspace_id),
            ).fetchone()

        if row is None:
            raise TableCatalogError(
                code="CATALOG_ENTRY_NOT_FOUND",
                message="Catalog entry not found",
                status_code=404,
            )

        return row

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            initialize_sqlite_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _assert_workspace_exists(self, conn: sqlite3.Connection, *, workspace_id: str) -> None:
        row = conn.execute(
            "SELECT id FROM workspaces WHERE id = ? AND status = 'active'",
            (workspace_id,),
        ).fetchone()
        if row is None:
            raise TableCatalogError(
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found",
                status_code=404,
            )

    def _ensure_user_record(self, conn: sqlite3.Connection, *, user_id: str) -> None:
        normalized_user = user_id.strip()
        if not normalized_user:
            raise TableCatalogError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )

        now = _utc_now()
        safe_local_part = re.sub(r"[^a-z0-9._-]+", "-", normalized_user.lower()).strip("-._") or "user"
        fallback_email = f"{safe_local_part}@local.invalid"

        conn.execute(
            """
            INSERT INTO users (id, email, display_name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at
            """,
            (normalized_user, fallback_email, normalized_user, now, now),
        )

    @staticmethod
    def _serialize_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "table_name": str(row["table_name"]),
            "human_label": str(row["human_label"]),
            "business_type": str(row["business_type"]),
            "write_mode": str(row["write_mode"]),
            "time_grain": str(row["time_grain"]),
            "primary_keys": _decode_json_list(row["primary_keys"]),
            "match_columns": _decode_json_list(row["match_columns"]),
            "is_active_target": bool(row["is_active_target"]),
            "description": str(row["description"]),
            "created_by": str(row["created_by"]),
            "updated_by": str(row["updated_by"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }


router = APIRouter(prefix="/workspaces/{workspace_id}/catalog", tags=["table-catalog"])


@router.post("")
async def create_table_catalog_entry(
    workspace_id: str,
    request: TableCatalogEntryCreateRequest,
    identity: AuthIdentity = Depends(require_permission("workspaces:write")),
) -> dict[str, Any]:
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="editor")
    service = get_table_catalog_service()
    try:
        entry = service.create_entry(
            workspace_id=workspace_id,
            actor_user_id=identity.user_id,
            payload=request,
        )
    except TableCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    return {"entry": entry}


@router.get("")
async def list_table_catalog_entries(
    workspace_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, Any]:
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="viewer")
    service = get_table_catalog_service()
    try:
        entries = service.list_entries(workspace_id=workspace_id)
    except TableCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    return {
        "count": len(entries),
        "entries": entries,
    }


@router.get("/active-target")
async def get_active_catalog_target(
    workspace_id: str,
    business_type: Literal["roster", "project_progress", "attendance", "other"],
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, Any]:
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="viewer")
    service = get_table_catalog_service()
    try:
        entry = service.get_active_target(workspace_id=workspace_id, business_type=business_type)
    except TableCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CATALOG_ACTIVE_TARGET_NOT_FOUND",
                "message": "No active catalog target found for the requested business type",
            },
        )

    return {"entry": entry}


@router.get("/{catalog_id}")
async def get_table_catalog_entry(
    workspace_id: str,
    catalog_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, Any]:
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="viewer")
    service = get_table_catalog_service()
    try:
        entry = service.get_entry(workspace_id=workspace_id, catalog_id=catalog_id)
    except TableCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    return {"entry": entry}


@router.patch("/{catalog_id}")
async def update_table_catalog_entry(
    workspace_id: str,
    catalog_id: str,
    request: TableCatalogEntryUpdateRequest,
    identity: AuthIdentity = Depends(require_permission("workspaces:write")),
) -> dict[str, Any]:
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="editor")
    service = get_table_catalog_service()
    try:
        entry = service.update_entry(
            workspace_id=workspace_id,
            catalog_id=catalog_id,
            actor_user_id=identity.user_id,
            payload=request,
        )
    except TableCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    return {"entry": entry}


@router.delete("/{catalog_id}")
async def delete_table_catalog_entry(
    workspace_id: str,
    catalog_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:manage")),
) -> dict[str, str]:
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="admin")
    service = get_table_catalog_service()
    try:
        service.delete_entry(workspace_id=workspace_id, catalog_id=catalog_id)
    except TableCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    return {"status": "deleted", "catalog_id": catalog_id}


def _assert_workspace_role(*, workspace_id: str, identity: AuthIdentity, minimum_role: str) -> str:
    workspace_service = get_workspace_service()
    try:
        return workspace_service.assert_workspace_access(
            workspace_id=workspace_id,
            user_id=identity.user_id,
            minimum_role=minimum_role,
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@lru_cache(maxsize=2)
def _cached_table_catalog_service(db_path: str) -> TableCatalogService:
    return TableCatalogService(db_path=Path(db_path).resolve())


def get_table_catalog_service() -> TableCatalogService:
    workspace_service = get_workspace_service()
    return _cached_table_catalog_service(str(workspace_service.db_path))


def clear_table_catalog_service_cache() -> None:
    _cached_table_catalog_service.cache_clear()


def _normalize_column_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        trimmed = value.strip()
        if not trimmed:
            continue
        lowered = trimmed.lower()
        if lowered not in normalized:
            normalized.append(lowered)
    return normalized


def _decode_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]

    if not isinstance(value, str):
        return []

    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(decoded, list):
        return []

    return [str(item) for item in decoded]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
