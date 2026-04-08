from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from threading import Lock
from typing import Any, Iterator

from pydantic import BaseModel, Field

from .chart_strategy import ChartStrategyRouter
from .config import get_settings
from .tool_calling import ToolCall, ToolCallRequest, ToolCallResponse, get_tool_calling_service


class ChatStreamRequest(BaseModel):
    user_id: str
    project_id: str
    dataset_table: str
    message: str | None = None
    conversation_id: str | None = None
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    role: str = "viewer"
    department: str | None = None
    clearance: int = 0
    last_event_id: int | None = None


@dataclass(slots=True)
class ChatEvent:
    id: int
    type: str
    payload: dict[str, Any]


@dataclass(slots=True)
class ChatSession:
    conversation_id: str
    next_event_id: int = 1
    events: list[ChatEvent] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


class ChatSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = Lock()

    def append_events(self, *, conversation_id: str, events: list[tuple[str, dict[str, Any]]]) -> list[ChatEvent]:
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                session = ChatSession(conversation_id=conversation_id)
                self._sessions[conversation_id] = session

            created: list[ChatEvent] = []
            for event_type, payload in events:
                event = ChatEvent(
                    id=session.next_event_id,
                    type=event_type,
                    payload=payload,
                )
                session.next_event_id += 1
                session.events.append(event)
                created.append(event)
            return created

    def events_after(self, *, conversation_id: str, last_event_id: int) -> list[ChatEvent]:
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                return []
            return [item for item in session.events if item.id > last_event_id]

    def get_context(self, *, conversation_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                session = ChatSession(conversation_id=conversation_id)
                self._sessions[conversation_id] = session
            return dict(session.context)

    def update_context(self, *, conversation_id: str, updates: dict[str, Any]) -> None:
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                session = ChatSession(conversation_id=conversation_id)
                self._sessions[conversation_id] = session
            session.context.update(updates)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


class ChatStreamService:
    def __init__(self) -> None:
        self.tool_service = get_tool_calling_service()
        self.router = ChartStrategyRouter()
        self.sessions = ChatSessionStore()

    def stream(
        self,
        request: ChatStreamRequest,
        *,
        last_event_id_header: str | None = None,
    ) -> Iterator[str]:
        conversation_id = request.conversation_id or uuid.uuid4().hex
        last_event_id = request.last_event_id
        if last_event_id is None and last_event_id_header:
            try:
                last_event_id = int(last_event_id_header)
            except ValueError:
                last_event_id = None

        replay_events: list[ChatEvent] = []
        if last_event_id is not None:
            replay_events = self.sessions.events_after(
                conversation_id=conversation_id,
                last_event_id=last_event_id,
            )

        new_events: list[ChatEvent] = []
        if request.message:
            generated = self._generate_event_payloads(request=request, conversation_id=conversation_id)
            new_events = self.sessions.append_events(conversation_id=conversation_id, events=generated)
        elif last_event_id is None:
            generated = [
                (
                    "final",
                    {
                        "conversation_id": conversation_id,
                        "request_id": request.request_id,
                        "status": "failed",
                        "text": "message is required when not replaying a previous stream",
                    },
                )
            ]
            new_events = self.sessions.append_events(conversation_id=conversation_id, events=generated)

        for event in [*replay_events, *new_events]:
            yield _format_sse(event)

    def clear_runtime_state(self) -> None:
        self.sessions.clear()

    def _generate_event_payloads(
        self,
        *,
        request: ChatStreamRequest,
        conversation_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        assert request.message is not None

        selected_tool, tool_args = self._select_tool(
            message=request.message,
            conversation_id=conversation_id,
        )
        reasoning_payload = {
            "conversation_id": conversation_id,
            "request_id": request.request_id,
            "text": f"Intent analyzed. Selected tool: {selected_tool}.",
            "tool_name": selected_tool,
        }

        tool_request = ToolCallRequest(
            conversation_id=conversation_id,
            request_id=request.request_id,
            idempotency_key=f"{request.request_id}:{selected_tool}",
            user_id=request.user_id,
            project_id=request.project_id,
            dataset_table=request.dataset_table,
            role=request.role,
            department=request.department,
            clearance=request.clearance,
            tool=ToolCall(name=selected_tool, arguments=tool_args),
        )
        tool_response = self.tool_service.invoke(tool_request)

        tool_payload = {
            "conversation_id": conversation_id,
            "request_id": request.request_id,
            "tool_name": selected_tool,
            "status": tool_response.status,
            "attempts": tool_response.attempts,
            "from_cache": tool_response.from_cache,
            "result": tool_response.result,
            "error": tool_response.error,
        }

        spec_payload, final_payload = self._build_spec_and_final(
            request=request,
            conversation_id=conversation_id,
            tool_response=tool_response,
            selected_tool=selected_tool,
        )

        return [
            ("reasoning", reasoning_payload),
            ("tool", tool_payload),
            ("spec", spec_payload),
            ("final", final_payload),
        ]

    def _select_tool(self, *, message: str, conversation_id: str) -> tuple[str, dict[str, Any]]:
        normalized = message.lower()
        if any(token in normalized for token in ["schema", "字段", "列", "describe", "数据集"]):
            return "describe_dataset", {"sample_limit": 10}

        if any(token in normalized for token in ["save", "保存", "bookmark"]):
            context = self.sessions.get_context(conversation_id=conversation_id)
            latest_spec = context.get("latest_spec")
            latest_sql = context.get("latest_sql")
            return "save_view", {
                "title": "Saved from Chat",
                "chart_spec": latest_spec,
                "sql": latest_sql,
                "conversation_id": conversation_id,
            }

        group_by: list[str] = []
        if "department" in normalized or "部门" in normalized:
            group_by.append("department")
        if "project" in normalized or "项目" in normalized:
            group_by.append("project")
        if "region" in normalized or "地区" in normalized:
            group_by.append("region")

        return "query_metrics", {
            "intent": message,
            "group_by": group_by,
        }

    def _build_spec_and_final(
        self,
        *,
        request: ChatStreamRequest,
        conversation_id: str,
        tool_response: ToolCallResponse,
        selected_tool: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if tool_response.status == "error":
            spec = {
                "conversation_id": conversation_id,
                "request_id": request.request_id,
                "spec": {
                    "engine": "recharts",
                    "chart_type": "empty",
                    "title": "No chart",
                    "data": [],
                    "config": {},
                    "route": {
                        "complexity_score": 0,
                        "threshold": self.router.COMPLEXITY_THRESHOLD,
                        "reasons": ["tool_execution_failed"],
                        "selected_engine": "recharts",
                    },
                },
            }
            final = {
                "conversation_id": conversation_id,
                "request_id": request.request_id,
                "status": "failed",
                "text": "Tool execution failed. Please refine the query and retry.",
            }
            return spec, final

        result = tool_response.result or {}

        if selected_tool == "query_metrics":
            metric = str(result.get("metric", "metric"))
            query_ast = result.get("query_ast", {}) if isinstance(result.get("query_ast"), dict) else {}
            group_by = query_ast.get("group_by", []) if isinstance(query_ast.get("group_by", []), list) else []
            rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
            chart_spec = self.router.build_spec(
                metric=metric,
                intent=request.message or "",
                rows=rows,
                group_by=[str(item) for item in group_by],
            )
            self.sessions.update_context(
                conversation_id=conversation_id,
                updates={
                    "latest_spec": chart_spec,
                    "latest_sql": result.get("sql"),
                    "latest_metric": metric,
                },
            )
            spec = {
                "conversation_id": conversation_id,
                "request_id": request.request_id,
                "spec": chart_spec,
            }
            final = {
                "conversation_id": conversation_id,
                "request_id": request.request_id,
                "status": "completed",
                "text": f"Query completed for metric {metric}, rows={result.get('row_count', 0)}.",
            }
            return spec, final

        if selected_tool == "describe_dataset":
            columns = result.get("columns", []) if isinstance(result.get("columns", []), list) else []
            sample_rows = result.get("sample_rows", []) if isinstance(result.get("sample_rows", []), list) else []
            chart_spec = {
                "engine": "recharts",
                "chart_type": "table",
                "title": f"{result.get('table', request.dataset_table)} overview",
                "data": sample_rows,
                "config": {
                    "columns": [item.get("name") for item in columns if isinstance(item, dict)],
                },
                "route": {
                    "complexity_score": 1,
                    "threshold": self.router.COMPLEXITY_THRESHOLD,
                    "reasons": ["dataset_profile_request"],
                    "selected_engine": "recharts",
                },
            }
            self.sessions.update_context(
                conversation_id=conversation_id,
                updates={"latest_spec": chart_spec},
            )
            spec = {
                "conversation_id": conversation_id,
                "request_id": request.request_id,
                "spec": chart_spec,
            }
            final = {
                "conversation_id": conversation_id,
                "request_id": request.request_id,
                "status": "completed",
                "text": f"Dataset described with {result.get('row_count', 0)} rows.",
            }
            return spec, final

        # save_view path
        chart_spec = {
            "engine": "recharts",
            "chart_type": "note",
            "title": "View saved",
            "data": [result],
            "config": {},
            "route": {
                "complexity_score": 1,
                "threshold": self.router.COMPLEXITY_THRESHOLD,
                "reasons": ["save_view_confirmation"],
                "selected_engine": "recharts",
            },
        }
        spec = {
            "conversation_id": conversation_id,
            "request_id": request.request_id,
            "spec": chart_spec,
        }
        final = {
            "conversation_id": conversation_id,
            "request_id": request.request_id,
            "status": "completed",
            "text": f"View saved: {result.get('view_id', 'unknown')}",
        }
        return spec, final


def _format_sse(event: ChatEvent) -> str:
    return (
        f"id: {event.id}\n"
        f"event: {event.type}\n"
        f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
    )


@lru_cache(maxsize=2)
def _cached_chat_stream_service(settings_key: str) -> ChatStreamService:
    _ = settings_key
    return ChatStreamService()


def get_chat_stream_service() -> ChatStreamService:
    settings = get_settings()
    return _cached_chat_stream_service(str(settings.upload_dir.resolve()))


def clear_chat_stream_service_cache() -> None:
    _cached_chat_stream_service.cache_clear()
