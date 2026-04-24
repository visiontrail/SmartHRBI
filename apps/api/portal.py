from __future__ import annotations

import uuid
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

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


@router.get("/workspaces")
async def list_portal_workspaces(user_id: str | None = Query(default=None)) -> dict[str, object]:
    store = get_published_page_store()
    pages = store.list_latest_by_workspace()
    summaries = get_workspace_service().list_workspace_summaries(
        workspace_ids=[page.workspace_id for page in pages],
        user_id=user_id,
    )
    summaries_by_id = {item["workspace_id"]: item for item in summaries}
    workspaces: list[dict[str, Any]] = []
    for page in pages:
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
                "thumbnail": None,
            }
        )
    return {
        "count": len(workspaces),
        "workspaces": workspaces,
    }


@router.get("/pages/{page_id}/manifest")
async def get_portal_manifest(page_id: str) -> dict[str, Any]:
    try:
        page = get_published_page_store().get(page_id=page_id)
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
async def get_portal_chart_data(page_id: str, chart_id: str) -> dict[str, Any]:
    try:
        page = get_published_page_store().get(page_id=page_id)
        return read_chart_data(page, chart_id=chart_id)
    except PublishedPageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.post("/pages/{page_id}/chat")
async def portal_page_chat(page_id: str, request: PortalChatRequest) -> StreamingResponse:
    try:
        page = get_published_page_store().get(page_id=page_id)
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
