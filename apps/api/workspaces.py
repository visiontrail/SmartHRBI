from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from .agentic_ingestion.schema import initialize_sqlite_schema
from .auth import AuthIdentity, require_permission
from .config import get_settings
from .published_pages import (
    PublishWorkspaceRequest,
    get_published_page_store,
    get_snapshot_writer,
)

SQLITE_RELATIVE_BASE = Path(__file__).resolve().parent
ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "editor": 1,
    "admin": 2,
    "owner": 3,
}


class WorkspaceError(Exception):
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


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workspace name cannot be empty")
        return normalized


class UpdateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Workspace name cannot be empty")
        return normalized


class AddWorkspaceMemberRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    role: str = Field(default="viewer")
    email: str | None = None
    display_name: str | None = None

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_id is required")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ROLE_RANK:
            raise ValueError("Unsupported workspace role")
        return normalized


@dataclass(slots=True)
class MemberRecord:
    user_id: str
    role: str


class WorkspaceService:
    def __init__(self, *, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize_schema()

    def create_workspace(self, *, owner_user_id: str, name: str) -> dict[str, str]:
        normalized_name = name.strip()
        if not normalized_name:
            raise WorkspaceError(
                code="WORKSPACE_NAME_REQUIRED",
                message="Workspace name is required",
                status_code=422,
            )

        normalized_owner = owner_user_id.strip()
        if not normalized_owner:
            raise WorkspaceError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )

        workspace_id = uuid.uuid4().hex

        with self._lock, self._connect() as conn:
            self._ensure_user(conn, user_id=normalized_owner, email=None, display_name=None)
            slug = self._allocate_slug(conn, normalized_name)
            now = _utc_now()

            conn.execute(
                """
                INSERT INTO workspaces (
                    id, name, slug, owner_user_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (workspace_id, normalized_name, slug, normalized_owner, now, now),
            )
            conn.execute(
                """
                INSERT INTO workspace_members (
                    id, workspace_id, user_id, role, created_at
                ) VALUES (?, ?, ?, 'owner', ?)
                """,
                (uuid.uuid4().hex, workspace_id, normalized_owner, now),
            )
            conn.commit()

        return {
            "workspace_id": workspace_id,
            "name": normalized_name,
            "slug": slug,
            "role": "owner",
        }

    def list_workspaces_for_user(self, *, user_id: str) -> list[dict[str, str]]:
        normalized_user = user_id.strip()
        if not normalized_user:
            return []

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    w.id,
                    w.name,
                    w.slug,
                    w.status,
                    w.created_at,
                    w.updated_at,
                    wm.role
                FROM workspaces AS w
                JOIN workspace_members AS wm
                  ON wm.workspace_id = w.id
                WHERE wm.user_id = ? AND w.status = 'active'
                ORDER BY w.updated_at DESC
                """,
                (normalized_user,),
            ).fetchall()

        return [self._serialize_workspace(row) for row in rows]

    def list_workspace_summaries(
        self,
        *,
        workspace_ids: list[str],
        user_id: str | None = None,
    ) -> list[dict[str, str]]:
        normalized_ids = [item.strip() for item in workspace_ids if item.strip()]
        if not normalized_ids:
            return []

        placeholders = ",".join("?" for _ in normalized_ids)
        params: list[str] = [*normalized_ids]
        user_join = ""
        user_where = ""
        if user_id is not None and user_id.strip():
            user_join = "JOIN workspace_members AS wm ON wm.workspace_id = w.id"
            user_where = "AND wm.user_id = ?"
            params.append(user_id.strip())

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT w.id, w.name, w.slug, w.status, w.created_at, w.updated_at
                FROM workspaces AS w
                {user_join}
                WHERE w.id IN ({placeholders}) AND w.status = 'active'
                {user_where}
                """,
                params,
            ).fetchall()

        summaries_by_id = {
            str(row["id"]): {
                "workspace_id": str(row["id"]),
                "name": str(row["name"]),
                "slug": str(row["slug"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        }
        return [summaries_by_id[item] for item in normalized_ids if item in summaries_by_id]

    def get_workspace_for_user(self, *, workspace_id: str, user_id: str) -> dict[str, str]:
        normalized_workspace_id = workspace_id.strip()
        normalized_user = user_id.strip()
        if not normalized_workspace_id or not normalized_user:
            raise WorkspaceError(
                code="WORKSPACE_FORBIDDEN",
                message="You do not have permission to access this workspace",
                status_code=403,
            )

        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    w.id,
                    w.name,
                    w.slug,
                    w.status,
                    w.created_at,
                    w.updated_at,
                    wm.role
                FROM workspaces AS w
                JOIN workspace_members AS wm
                  ON wm.workspace_id = w.id
                WHERE w.id = ? AND wm.user_id = ? AND w.status = 'active'
                """,
                (normalized_workspace_id, normalized_user),
            ).fetchone()

        if row is None:
            raise WorkspaceError(
                code="WORKSPACE_FORBIDDEN",
                message="You do not have permission to access this workspace",
                status_code=403,
            )

        return self._serialize_workspace(row)

    def assert_workspace_access(
        self,
        *,
        workspace_id: str,
        user_id: str,
        minimum_role: str = "viewer",
    ) -> str:
        normalized_workspace_id = workspace_id.strip()
        normalized_user = user_id.strip()
        normalized_minimum_role = minimum_role.strip().lower()

        if normalized_minimum_role not in ROLE_RANK:
            raise WorkspaceError(
                code="WORKSPACE_ROLE_INVALID",
                message="Unsupported workspace role requirement",
                status_code=500,
            )

        with self._lock, self._connect() as conn:
            member = self._get_member(conn, workspace_id=normalized_workspace_id, user_id=normalized_user)

        if member is None:
            raise WorkspaceError(
                code="WORKSPACE_FORBIDDEN",
                message="You do not have permission to access this workspace",
                status_code=403,
            )

        if ROLE_RANK[member.role] < ROLE_RANK[normalized_minimum_role]:
            raise WorkspaceError(
                code="WORKSPACE_FORBIDDEN",
                message="You do not have permission to access this workspace",
                status_code=403,
            )

        return member.role

    def rename_workspace(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        name: str,
    ) -> dict[str, str]:
        normalized_workspace_id = workspace_id.strip()
        normalized_actor = actor_user_id.strip()
        normalized_name = name.strip()

        if not normalized_name:
            raise WorkspaceError(
                code="WORKSPACE_NAME_REQUIRED",
                message="Workspace name is required",
                status_code=422,
            )

        with self._lock, self._connect() as conn:
            actor_member = self._get_member(
                conn,
                workspace_id=normalized_workspace_id,
                user_id=normalized_actor,
            )
            if actor_member is None or ROLE_RANK[actor_member.role] < ROLE_RANK["editor"]:
                raise WorkspaceError(
                    code="WORKSPACE_FORBIDDEN",
                    message="You do not have permission to access this workspace",
                    status_code=403,
                )

            workspace_row = conn.execute(
                """
                SELECT id, slug, status, created_at, updated_at
                FROM workspaces
                WHERE id = ?
                """,
                (normalized_workspace_id,),
            ).fetchone()
            if workspace_row is None or str(workspace_row["status"]) != "active":
                raise WorkspaceError(
                    code="WORKSPACE_NOT_FOUND",
                    message="Workspace not found",
                    status_code=404,
                )

            now = _utc_now()
            conn.execute(
                """
                UPDATE workspaces
                SET name = ?, updated_at = ?
                WHERE id = ?
                """,
                (normalized_name, now, normalized_workspace_id),
            )
            conn.commit()

            return {
                "workspace_id": normalized_workspace_id,
                "name": normalized_name,
                "slug": str(workspace_row["slug"]),
                "status": "active",
                "role": actor_member.role,
                "created_at": str(workspace_row["created_at"]),
                "updated_at": now,
            }

    def deactivate_workspace(self, *, workspace_id: str, actor_user_id: str) -> dict[str, str]:
        normalized_workspace_id = workspace_id.strip()
        normalized_actor = actor_user_id.strip()
        updated_at = _utc_now()

        with self._lock, self._connect() as conn:
            actor_member = self._get_member(
                conn,
                workspace_id=normalized_workspace_id,
                user_id=normalized_actor,
            )
            if actor_member is None or ROLE_RANK[actor_member.role] < ROLE_RANK["admin"]:
                raise WorkspaceError(
                    code="WORKSPACE_FORBIDDEN",
                    message="You do not have permission to access this workspace",
                    status_code=403,
                )

            workspace_row = conn.execute(
                """
                SELECT id, status
                FROM workspaces
                WHERE id = ?
                """,
                (normalized_workspace_id,),
            ).fetchone()
            if workspace_row is None or str(workspace_row["status"]) != "active":
                raise WorkspaceError(
                    code="WORKSPACE_NOT_FOUND",
                    message="Workspace not found",
                    status_code=404,
                )

            conn.execute(
                """
                UPDATE workspaces
                SET status = 'inactive', updated_at = ?
                WHERE id = ?
                """,
                (updated_at, normalized_workspace_id),
            )
            conn.commit()

        return {
            "workspace_id": normalized_workspace_id,
            "status": "inactive",
            "updated_at": updated_at,
        }

    def add_member(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        member_user_id: str,
        role: str,
        email: str | None,
        display_name: str | None,
    ) -> dict[str, str]:
        normalized_workspace_id = workspace_id.strip()
        normalized_actor = actor_user_id.strip()
        normalized_member = member_user_id.strip()
        normalized_role = role.strip().lower()

        if normalized_role not in ROLE_RANK:
            raise WorkspaceError(
                code="WORKSPACE_ROLE_INVALID",
                message="Unsupported workspace role",
                status_code=422,
            )

        with self._lock, self._connect() as conn:
            actor_member = self._get_member(
                conn,
                workspace_id=normalized_workspace_id,
                user_id=normalized_actor,
            )
            if actor_member is None or ROLE_RANK[actor_member.role] < ROLE_RANK["admin"]:
                raise WorkspaceError(
                    code="WORKSPACE_FORBIDDEN",
                    message="You do not have permission to manage workspace members",
                    status_code=403,
                )

            workspace_exists = conn.execute(
                "SELECT id FROM workspaces WHERE id = ?",
                (normalized_workspace_id,),
            ).fetchone()
            if workspace_exists is None:
                raise WorkspaceError(
                    code="WORKSPACE_NOT_FOUND",
                    message="Workspace not found",
                    status_code=404,
                )

            self._ensure_user(
                conn,
                user_id=normalized_member,
                email=email,
                display_name=display_name,
            )

            existing_member = self._get_member(
                conn,
                workspace_id=normalized_workspace_id,
                user_id=normalized_member,
            )
            if existing_member is None:
                conn.execute(
                    """
                    INSERT INTO workspace_members (
                        id, workspace_id, user_id, role, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        normalized_workspace_id,
                        normalized_member,
                        normalized_role,
                        _utc_now(),
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE workspace_members
                    SET role = ?
                    WHERE workspace_id = ? AND user_id = ?
                    """,
                    (normalized_role, normalized_workspace_id, normalized_member),
                )

            conn.commit()

        return {
            "workspace_id": normalized_workspace_id,
            "user_id": normalized_member,
            "role": normalized_role,
        }

    def list_members(self, *, workspace_id: str, actor_user_id: str) -> list[dict[str, str]]:
        normalized_workspace_id = workspace_id.strip()
        normalized_actor = actor_user_id.strip()

        with self._lock, self._connect() as conn:
            actor_member = self._get_member(
                conn,
                workspace_id=normalized_workspace_id,
                user_id=normalized_actor,
            )
            if actor_member is None:
                raise WorkspaceError(
                    code="WORKSPACE_FORBIDDEN",
                    message="You do not have permission to access this workspace",
                    status_code=403,
                )

            rows = conn.execute(
                """
                SELECT
                    wm.user_id,
                    wm.role,
                    COALESCE(u.display_name, wm.user_id) AS display_name,
                    COALESCE(u.email, '') AS email
                FROM workspace_members AS wm
                LEFT JOIN users AS u
                  ON u.id = wm.user_id
                WHERE wm.workspace_id = ?
                ORDER BY CASE wm.role
                    WHEN 'owner' THEN 4
                    WHEN 'admin' THEN 3
                    WHEN 'editor' THEN 2
                    ELSE 1
                END DESC,
                wm.user_id ASC
                """,
                (normalized_workspace_id,),
            ).fetchall()

        return [
            {
                "user_id": str(row["user_id"]),
                "role": str(row["role"]),
                "display_name": str(row["display_name"]),
                "email": str(row["email"]),
            }
            for row in rows
        ]

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            initialize_sqlite_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _allocate_slug(self, conn: sqlite3.Connection, name: str) -> str:
        base = _slugify(name)
        if not base:
            base = "workspace"

        candidate = base
        index = 2
        while True:
            row = conn.execute(
                "SELECT 1 FROM workspaces WHERE slug = ?",
                (candidate,),
            ).fetchone()
            if row is None:
                return candidate
            candidate = f"{base}-{index}"
            index += 1

    def _ensure_user(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        email: str | None,
        display_name: str | None,
    ) -> None:
        normalized_user = user_id.strip()
        if not normalized_user:
            raise WorkspaceError(
                code="USER_ID_REQUIRED",
                message="user_id is required",
                status_code=422,
            )

        normalized_email = _normalize_email(normalized_user, email)
        normalized_display_name = (display_name or normalized_user).strip() or normalized_user
        now = _utc_now()

        conn.execute(
            """
            INSERT INTO users (id, email, display_name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email = excluded.email,
                display_name = excluded.display_name,
                updated_at = excluded.updated_at
            """,
            (normalized_user, normalized_email, normalized_display_name, now, now),
        )

    def _get_member(
        self,
        conn: sqlite3.Connection,
        *,
        workspace_id: str,
        user_id: str,
    ) -> MemberRecord | None:
        row = conn.execute(
            """
            SELECT wm.user_id, wm.role
            FROM workspace_members AS wm
            JOIN workspaces AS w
              ON w.id = wm.workspace_id
            WHERE wm.workspace_id = ? AND wm.user_id = ? AND w.status = 'active'
            """,
            (workspace_id, user_id),
        ).fetchone()
        if row is None:
            return None

        return MemberRecord(
            user_id=str(row["user_id"]),
            role=str(row["role"]),
        )

    @staticmethod
    def _serialize_workspace(row: sqlite3.Row) -> dict[str, str]:
        return {
            "workspace_id": str(row["id"]),
            "name": str(row["name"]),
            "slug": str(row["slug"]),
            "status": str(row["status"]),
            "role": str(row["role"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }


router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("")
async def create_workspace(
    request: CreateWorkspaceRequest,
    identity: AuthIdentity = Depends(require_permission("workspaces:write")),
) -> dict[str, str]:
    service = get_workspace_service()
    try:
        return service.create_workspace(owner_user_id=identity.user_id, name=request.name)
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.get("")
async def list_workspaces(
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, object]:
    service = get_workspace_service()
    workspaces = service.list_workspaces_for_user(user_id=identity.user_id)
    return {
        "count": len(workspaces),
        "workspaces": workspaces,
    }


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, str]:
    service = get_workspace_service()
    try:
        return service.get_workspace_for_user(workspace_id=workspace_id, user_id=identity.user_id)
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.patch("/{workspace_id}")
async def rename_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    identity: AuthIdentity = Depends(require_permission("workspaces:write")),
) -> dict[str, str]:
    service = get_workspace_service()
    try:
        return service.rename_workspace(
            workspace_id=workspace_id,
            actor_user_id=identity.user_id,
            name=request.name,
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:manage")),
) -> dict[str, str]:
    service = get_workspace_service()
    try:
        return service.deactivate_workspace(
            workspace_id=workspace_id,
            actor_user_id=identity.user_id,
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.get("/{workspace_id}/members")
async def list_workspace_members(
    workspace_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, object]:
    service = get_workspace_service()
    try:
        members = service.list_members(workspace_id=workspace_id, actor_user_id=identity.user_id)
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    return {
        "count": len(members),
        "members": members,
    }


@router.post("/{workspace_id}/members")
async def add_workspace_member(
    workspace_id: str,
    request: AddWorkspaceMemberRequest,
    identity: AuthIdentity = Depends(require_permission("workspaces:manage")),
) -> dict[str, str]:
    service = get_workspace_service()
    try:
        return service.add_member(
            workspace_id=workspace_id,
            actor_user_id=identity.user_id,
            member_user_id=request.user_id,
            role=request.role,
            email=request.email,
            display_name=request.display_name,
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/{workspace_id}/publish")
async def publish_workspace(
    workspace_id: str,
    request: PublishWorkspaceRequest,
    identity: AuthIdentity = Depends(require_permission("workspaces:write")),
) -> dict[str, object]:
    service = get_workspace_service()
    try:
        service.assert_workspace_access(
            workspace_id=workspace_id,
            user_id=identity.user_id,
            minimum_role="editor",
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    empty_charts = [chart.chart_id for chart in request.charts if not chart.rows]
    if empty_charts:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PUBLISH_CHART_DATA_REQUIRED",
                "message": "All charts must have data before publishing",
                "chart_ids": empty_charts,
            },
        )

    store = get_published_page_store()
    writer = get_snapshot_writer()
    version = store.next_version(workspace_id=workspace_id)
    published_at = _utc_now()
    snapshot = writer.write(
        workspace_id=workspace_id,
        version=version,
        layout=request.layout,
        sidebar=request.sidebar,
        charts=request.charts,
        actor_role=identity.role,
        published_at=published_at,
    )
    page = store.create(
        workspace_id=workspace_id,
        version=version,
        published_by=identity.user_id,
        manifest_path=snapshot.manifest_path,
        published_at=published_at,
    )
    return {
        "published_page_id": page.id,
        "version": page.version,
    }


@router.get("/{workspace_id}/published")
async def list_workspace_published_pages(
    workspace_id: str,
    identity: AuthIdentity = Depends(require_permission("workspaces:read")),
) -> dict[str, object]:
    service = get_workspace_service()
    try:
        service.assert_workspace_access(
            workspace_id=workspace_id,
            user_id=identity.user_id,
            minimum_role="viewer",
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    pages = get_published_page_store().list_by_workspace(workspace_id=workspace_id)
    history = [page.to_history_item() for page in pages]
    return {
        "count": len(history),
        "published_pages": history,
    }


@lru_cache(maxsize=2)
def _cached_workspace_service(storage_key: str) -> WorkspaceService:
    parsed = urlparse(storage_key)
    if parsed.scheme == "sqlite":
        db_path = _sqlite_db_path_from_url(storage_key)
    else:
        state_root = Path(storage_key)
        state_root.mkdir(parents=True, exist_ok=True)
        db_path = state_root / "workspace_state.sqlite3"

    return WorkspaceService(db_path=db_path)


def get_workspace_service() -> WorkspaceService:
    settings = get_settings()
    db_url = settings.database_url.strip()
    if db_url.startswith("sqlite://"):
        storage_key = db_url
    else:
        storage_key = str((settings.upload_dir / "state").resolve())
    return _cached_workspace_service(storage_key)


def clear_workspace_service_cache() -> None:
    _cached_workspace_service.cache_clear()


def _sqlite_db_path_from_url(database_url: str) -> Path:
    parsed = urlparse(database_url)
    raw_path = unquote(parsed.path)

    if raw_path.startswith("//"):
        return Path("/" + raw_path.lstrip("/")).resolve()

    if raw_path.startswith("/"):
        raw_path = raw_path[1:]

    return (SQLITE_RELATIVE_BASE / raw_path).resolve()


def _slugify(raw: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", raw.strip().lower())
    compact = compact.strip("-")
    if len(compact) > 56:
        return compact[:56].rstrip("-")
    return compact


def _normalize_email(user_id: str, email: str | None) -> str:
    candidate = (email or "").strip().lower()
    if candidate and "@" in candidate:
        return candidate

    user_candidate = user_id.strip().lower()
    if "@" in user_candidate:
        return user_candidate

    safe_local_part = re.sub(r"[^a-z0-9._-]+", "-", user_candidate)
    safe_local_part = safe_local_part.strip("-._") or "user"
    return f"{safe_local_part}@local.invalid"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
