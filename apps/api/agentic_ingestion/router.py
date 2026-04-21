from __future__ import annotations

from typing import Any

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth import AuthIdentity, require_permission
from ..audit import get_audit_logger
from ..workspaces import WorkspaceError, get_workspace_service
from .models import (
    IngestionApproveRequest,
    IngestionExecuteRequest,
    IngestionHealth,
    IngestionPlanRequest,
    IngestionSetupConfirmRequest,
)
from .runtime import IngestionPlanningError, WriteIngestionAgentRuntime
from .uploads import IngestionUploadError, get_ingestion_upload_service

router = APIRouter(prefix="/ingestion", tags=["agentic-ingestion"])
runtime = WriteIngestionAgentRuntime()


@router.get("/healthz")
async def ingestion_healthz() -> IngestionHealth:
    return IngestionHealth(stage=runtime.stage, message=runtime.health_summary())


@router.post("/uploads")
async def create_ingestion_upload(
    workspace_id: str = Form(...),
    files: list[UploadFile] = File(...),
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, Any]:
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
    _assert_workspace_role(
        workspace_id=request.workspace_id,
        identity=identity,
        minimum_role="editor",
    )

    try:
        return await anyio.to_thread.run_sync(
            lambda: runtime.build_plan(
                workspace_id=request.workspace_id,
                job_id=request.job_id,
                requested_by=identity.user_id,
                conversation_id=request.conversation_id,
                message=request.message,
            )
        )
    except IngestionPlanningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/setup/confirm")
async def confirm_ingestion_setup(
    request: IngestionSetupConfirmRequest,
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, Any]:
    _assert_workspace_role(
        workspace_id=request.workspace_id,
        identity=identity,
        minimum_role="editor",
    )

    try:
        return await anyio.to_thread.run_sync(
            lambda: runtime.confirm_setup(
                workspace_id=request.workspace_id,
                job_id=request.job_id,
                requested_by=identity.user_id,
                setup_seed=request.setup,
                conversation_id=request.conversation_id,
                message=request.message,
            )
        )
    except IngestionPlanningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/approve")
async def approve_ingestion_proposal(
    request: IngestionApproveRequest,
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, Any]:
    _assert_workspace_role(
        workspace_id=request.workspace_id,
        identity=identity,
        minimum_role="editor",
    )

    try:
        payload = runtime.approve_plan(
            workspace_id=request.workspace_id,
            job_id=request.job_id,
            proposal_id=request.proposal_id,
            approved_action=request.approved_action,
            approved_by=identity.user_id,
            user_overrides=request.user_overrides,
        )
    except IngestionPlanningError as exc:
        get_audit_logger().log(
            event_type="ingestion",
            action="approve",
            status="failed",
            severity="WARN",
            user_id=identity.user_id,
            project_id=identity.project_id,
            resource=request.job_id,
            detail={"code": exc.code, "workspace_id": request.workspace_id},
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    get_audit_logger().log(
        event_type="ingestion",
        action="approve",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        resource=request.job_id,
        detail={
            "workspace_id": request.workspace_id,
            "proposal_id": request.proposal_id,
            "approved_action": request.approved_action,
        },
    )
    return payload


@router.post("/execute")
async def execute_ingestion_plan(
    request: IngestionExecuteRequest,
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, Any]:
    _assert_workspace_role(
        workspace_id=request.workspace_id,
        identity=identity,
        minimum_role="editor",
    )

    try:
        payload = runtime.execute_plan(
            workspace_id=request.workspace_id,
            job_id=request.job_id,
            proposal_id=request.proposal_id,
            executed_by=identity.user_id,
        )
    except IngestionPlanningError as exc:
        get_audit_logger().log(
            event_type="ingestion",
            action="execute",
            status="failed",
            severity="WARN",
            user_id=identity.user_id,
            project_id=identity.project_id,
            resource=request.job_id,
            detail={"code": exc.code, "workspace_id": request.workspace_id},
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    get_audit_logger().log(
        event_type="ingestion",
        action="execute",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        resource=request.job_id,
        detail={
            "workspace_id": request.workspace_id,
            "proposal_id": request.proposal_id,
            "execution_id": payload.get("execution_id"),
        },
    )
    return payload


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
