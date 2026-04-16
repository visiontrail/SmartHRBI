from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth import AuthIdentity, require_permission
from ..config import get_settings
from ..workspaces import WorkspaceError, get_workspace_service
from .feature_flags import ensure_agentic_ingestion_enabled
from .models import IngestionHealth, IngestionPlanRequest
from .runtime import IngestionPlanningError, WriteIngestionAgentRuntime
from .uploads import IngestionUploadError, get_ingestion_upload_service

router = APIRouter(prefix="/ingestion", tags=["agentic-ingestion"])
runtime = WriteIngestionAgentRuntime()


@router.get("/healthz")
async def ingestion_healthz() -> IngestionHealth:
    settings = get_settings()
    ensure_agentic_ingestion_enabled(settings.agentic_ingestion_enabled)

    return IngestionHealth(stage=runtime.stage, message=runtime.health_summary())


@router.post("/uploads")
async def create_ingestion_upload(
    workspace_id: str = Form(...),
    files: list[UploadFile] = File(...),
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, Any]:
    settings = get_settings()
    ensure_agentic_ingestion_enabled(settings.agentic_ingestion_enabled)
    _assert_workspace_role(workspace_id=workspace_id, identity=identity, minimum_role="editor")

    service = get_ingestion_upload_service()
    try:
        return await service.create_upload_inspection(
            workspace_id=workspace_id,
            uploaded_by=identity.user_id,
            files=files,
        )
    except IngestionUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/plan")
async def create_ingestion_plan(
    request: IngestionPlanRequest,
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, Any]:
    settings = get_settings()
    ensure_agentic_ingestion_enabled(settings.agentic_ingestion_enabled)
    _assert_workspace_role(
        workspace_id=request.workspace_id,
        identity=identity,
        minimum_role="editor",
    )

    try:
        return runtime.build_plan(
            workspace_id=request.workspace_id,
            job_id=request.job_id,
            requested_by=identity.user_id,
            conversation_id=request.conversation_id,
            message=request.message,
        )
    except IngestionPlanningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


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
