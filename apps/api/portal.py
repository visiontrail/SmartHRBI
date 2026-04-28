from __future__ import annotations

import uuid
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from .auth import AuthIdentity, get_current_identity
from .chart_query_agent import ChartQueryAgent, ChartQueryAgentError, format_sse
from .published_pages import (
    PublishedPageError,
    get_published_page_store,
    read_chart_data,
    read_manifest,
)
from .workspaces import get_workspace_service

router = APIRouter(prefix="/portal", tags=["portal"])


class PortalChatRequest(BaseModel):
    message: str = Field(min_length=1)
    chart_id: str | None = None
    conversation_id: str | None = None
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


def _get_user_workspace_roles(user_id: str) -> dict[str, str]:
    """Returns {workspace_id: role} for workspaces the user is a member of."""
    workspaces = get_workspace_service().list_workspaces_for_user(user_id=user_id)
    return {w["workspace_id"]: w["role"] for w in workspaces}


@router.get("/workspaces")
async def list_portal_workspaces(
    identity: AuthIdentity = Depends(get_current_identity),
) -> dict[str, object]:
    store = get_published_page_store()
    pages = store.list_latest_by_workspace()
    user_roles = _get_user_workspace_roles(identity.user_id)

    workspaces: list[dict[str, Any]] = []
    workspace_ids_to_fetch: list[str] = []
    visible_pages = []

    for page in pages:
        ws_roles: set[str] = set()
        ws_role = user_roles.get(page.workspace_id)
        if ws_role:
            ws_roles.add(ws_role)

        if page.is_visible_to(user_id=identity.user_id, workspace_member_roles=ws_roles):
            visible_pages.append(page)
            workspace_ids_to_fetch.append(page.workspace_id)

    summaries = get_workspace_service().list_workspace_summaries(
        workspace_ids=workspace_ids_to_fetch,
    )
    summaries_by_id = {item["workspace_id"]: item for item in summaries}

    for page in visible_pages:
        summary = summaries_by_id.get(page.workspace_id)
        if summary is None:
            continue
        workspaces.append(
            {
                "workspace_id": page.workspace_id,
                "name": summary["name"],
                "slug": summary["slug"],
                "latest_page_id": page.id,
                "latest_version": page.version,
                "published_at": page.published_at,
                "published_by": page.published_by,
                "visibility_mode": page.visibility_mode,
                "thumbnail": None,
            }
        )

    return {
        "count": len(workspaces),
        "workspaces": workspaces,
    }


def _assert_page_visible(page_id: str, identity: AuthIdentity) -> Any:
    store = get_published_page_store()
    try:
        page = store.get(page_id=page_id)
    except PublishedPageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    user_roles = _get_user_workspace_roles(identity.user_id)
    ws_roles: set[str] = set()
    ws_role = user_roles.get(page.workspace_id)
    if ws_role:
        ws_roles.add(ws_role)

    if not page.is_visible_to(user_id=identity.user_id, workspace_member_roles=ws_roles):
        raise HTTPException(
            status_code=403,
            detail={"code": "page_not_visible", "message": "You do not have access to this page"},
        )
    return page


@router.get("/pages/{page_id}/manifest")
async def get_portal_manifest(
    page_id: str,
    identity: AuthIdentity = Depends(get_current_identity),
) -> dict[str, Any]:
    page = _assert_page_visible(page_id, identity)
    try:
        manifest = read_manifest(page)
    except PublishedPageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
    return {
        "page_id": page.id,
        "workspace_id": page.workspace_id,
        "version": page.version,
        "published_at": page.published_at,
        "manifest": manifest,
    }


@router.get("/pages/{page_id}/charts/{chart_id}/data")
async def get_portal_chart_data(
    page_id: str,
    chart_id: str,
    identity: AuthIdentity = Depends(get_current_identity),
) -> dict[str, Any]:
    page = _assert_page_visible(page_id, identity)
    try:
        return read_chart_data(page, chart_id=chart_id)
    except PublishedPageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/pages/{page_id}/chat")
async def portal_page_chat(
    page_id: str,
    request: PortalChatRequest,
    identity: AuthIdentity = Depends(get_current_identity),
) -> StreamingResponse:
    page = _assert_page_visible(page_id, identity)
    try:
        manifest = read_manifest(page)
    except PublishedPageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    _ = manifest
    agent = ChartQueryAgent()

    def event_stream() -> Iterator[str]:
        conversation_id = request.conversation_id or uuid.uuid4().hex
        try:
            events = agent.run_turn(
                page=page,
                message=request.message,
                request_id=request.request_id,
                conversation_id=conversation_id,
                chart_id=request.chart_id,
            )
        except ChartQueryAgentError as exc:
            events = [
                (
                    "error",
                    {
                        "conversation_id": conversation_id,
                        "request_id": request.request_id,
                        "status": "failed",
                        "code": exc.code,
                        "message": exc.message,
                    },
                ),
                (
                    "final",
                    {
                        "conversation_id": conversation_id,
                        "request_id": request.request_id,
                        "status": "failed",
                        "text": exc.message,
                    },
                ),
            ]
        for event_type, payload in events:
            yield format_sse(event_type, payload)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
