from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from threading import Lock
from typing import Any, Iterator

from pydantic import BaseModel, Field

from .agent_guardrails import AgentGuardrailError
from .agent_runtime import AgentRequest, AgentRuntimeError, get_agent_runtime
from .chart_strategy import ChartStrategyRouter
from .config import get_settings
from .llm_openai import OpenAICompatibleToolSelector, ToolSelectionError
from .semantic import get_semantic_registry
from .tool_calling import ToolCall, ToolCallRequest, ToolCallResponse, get_tool_calling_service

logger = logging.getLogger("smarthrbi.chat")


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
        settings = get_settings()
        self.settings = settings
        self.tool_service = get_tool_calling_service()
        self.agent_runtime = get_agent_runtime()
        self.router = ChartStrategyRouter()
        self.sessions = ChatSessionStore()
        self.llm_selector = OpenAICompatibleToolSelector(
            base_url=settings.model_provider_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            metric_catalog=get_semantic_registry().list_metrics(),
        )

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
            try:
                generated = self._generate_event_payloads(request=request, conversation_id=conversation_id)
            except Exception:
                logger.exception(
                    "chat_stream_generation_failed conversation_id=%s request_id=%s",
                    conversation_id,
                    request.request_id,
                )
                generated = self._build_terminal_failure_events(
                    conversation_id=conversation_id,
                    request_id=request.request_id,
                    text="Unable to process the request right now. Please retry.",
                )
            new_events = self.sessions.append_events(conversation_id=conversation_id, events=generated)
        elif last_event_id is None:
            generated = self._build_terminal_failure_events(
                conversation_id=conversation_id,
                request_id=request.request_id,
                text="message is required when not replaying a previous stream",
            )
            new_events = self.sessions.append_events(conversation_id=conversation_id, events=generated)

        for event in [*replay_events, *new_events]:
            yield _format_sse(event)

    def clear_runtime_state(self) -> None:
        self.sessions.clear()
        self.agent_runtime.clear_runtime_state()

    def _generate_event_payloads(
        self,
        *,
        request: ChatStreamRequest,
        conversation_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        engine = self._resolve_chat_engine(request)
        if engine == "deterministic":
            return self._generate_deterministic_event_payloads(request=request, conversation_id=conversation_id)

        if engine == "agent_shadow":
            deterministic_events = self._generate_deterministic_event_payloads(
                request=request,
                conversation_id=conversation_id,
            )
            try:
                shadow_result = self._generate_agent_event_payloads(
                    request=request,
                    conversation_id=conversation_id,
                )
                self.sessions.update_context(
                    conversation_id=conversation_id,
                    updates={"shadow_agent_events": shadow_result},
                )
            except Exception:
                logger.exception(
                    "agent_shadow_failed conversation_id=%s request_id=%s",
                    conversation_id,
                    request.request_id,
                )
            return deterministic_events

        try:
            return self._generate_agent_event_payloads(request=request, conversation_id=conversation_id)
        except AgentGuardrailError as exc:
            logger.warning(
                "agent_guardrail_blocked conversation_id=%s request_id=%s code=%s",
                conversation_id,
                request.request_id,
                exc.code,
            )
            return [
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
        except AgentRuntimeError as exc:
            logger.warning(
                "agent_runtime_failed conversation_id=%s request_id=%s code=%s fallback=%s",
                conversation_id,
                request.request_id,
                exc.code,
                exc.should_fallback,
            )
            return [
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

        return self._generate_deterministic_event_payloads(request=request, conversation_id=conversation_id)

    def _generate_agent_event_payloads(
        self,
        *,
        request: ChatStreamRequest,
        conversation_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        assert request.message is not None
        result = self.agent_runtime.run_turn(
            AgentRequest(
                conversation_id=conversation_id,
                request_id=request.request_id,
                user_id=request.user_id,
                project_id=request.project_id,
                dataset_table=request.dataset_table,
                message=request.message,
                role=request.role,
                department=request.department,
                clearance=request.clearance,
            )
        )
        self.sessions.update_context(
            conversation_id=conversation_id,
            updates={
                "latest_spec": result.spec,
                "latest_sql": result.ai_state.get("latest_result", {}).get("sql")
                if isinstance(result.ai_state.get("latest_result"), dict)
                else None,
                "agent_session_id": result.agent_session_id,
                "agent_tool_trace": result.tool_trace,
            },
        )
        return result.events

    def _generate_deterministic_event_payloads(
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
        logger.info(
            "chat_tool_selected conversation_id=%s request_id=%s tool_name=%s arguments=%s",
            conversation_id,
            request.request_id,
            selected_tool,
            json.dumps(tool_args, ensure_ascii=False, default=str),
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
        logger.info(
            "chat_tool_result conversation_id=%s request_id=%s tool_name=%s status=%s attempts=%s from_cache=%s result_summary=%s error=%s",
            conversation_id,
            request.request_id,
            selected_tool,
            tool_response.status,
            tool_response.attempts,
            tool_response.from_cache,
            json.dumps(_summarize_tool_result(tool_response.result), ensure_ascii=False, default=str),
            json.dumps(tool_response.error, ensure_ascii=False, default=str),
        )

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

    def _resolve_chat_engine(self, request: ChatStreamRequest) -> str:
        engine = self.settings.chat_engine
        allowlist = self.settings.chat_engine_user_allowlist
        if allowlist and request.user_id not in allowlist:
            return "deterministic"
        return engine

    def _select_tool(self, *, message: str, conversation_id: str) -> tuple[str, dict[str, Any]]:
        context = self.sessions.get_context(conversation_id=conversation_id)
        if self.llm_selector.enabled:
            try:
                selected = self.llm_selector.select_tool(
                    message=message,
                    conversation_id=conversation_id,
                    context=context,
                )
                return selected.tool_name, selected.arguments
            except ToolSelectionError as exc:
                logger.warning(
                    "chat_tool_selection_fallback conversation_id=%s message=%r reason=%s context=%s",
                    conversation_id,
                    message,
                    exc.message,
                    json.dumps(context, ensure_ascii=False, default=str),
                )
                # Fallback to deterministic rule routing if LLM routing is unavailable.
            except Exception:
                logger.exception(
                    "chat_tool_selection_unexpected_error conversation_id=%s",
                    conversation_id,
                )

        return self._select_tool_with_rules(message=message, conversation_id=conversation_id)

    def _select_tool_with_rules(self, *, message: str, conversation_id: str) -> tuple[str, dict[str, Any]]:
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

    def _build_terminal_failure_events(
        self,
        *,
        conversation_id: str,
        request_id: str,
        text: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        return [
            (
                "final",
                {
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "status": "failed",
                    "text": text,
                },
            )
        ]


def _format_sse(event: ChatEvent) -> str:
    return (
        f"id: {event.id}\n"
        f"event: {event.type}\n"
        f"data: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
    )


def _summarize_tool_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    summary: dict[str, Any] = {}
    if "metric" in result:
        summary["metric"] = result.get("metric")
    if "row_count" in result:
        summary["row_count"] = result.get("row_count")
    rows = result.get("rows")
    if isinstance(rows, list):
        summary["rows_preview_count"] = min(len(rows), 3)
        summary["rows_preview"] = rows[:3]
    if "sql" in result:
        summary["sql"] = result.get("sql")
    if "table" in result:
        summary["table"] = result.get("table")
    columns = result.get("columns")
    if isinstance(columns, list):
        summary["columns"] = columns[:10]
    if "view_id" in result:
        summary["view_id"] = result.get("view_id")
    if "share_path" in result:
        summary["share_path"] = result.get("share_path")
    return summary


@lru_cache(maxsize=2)
def _cached_chat_stream_service(settings_key: str) -> ChatStreamService:
    _ = settings_key
    return ChatStreamService()


def get_chat_stream_service() -> ChatStreamService:
    settings = get_settings()
    settings_key = "|".join(
        [
            str(settings.upload_dir.resolve()),
            settings.model_provider_url.strip(),
            settings.ai_model.strip(),
            "enabled" if bool(settings.ai_api_key.strip()) else "disabled",
            settings.chat_engine,
            ",".join(sorted(settings.chat_engine_user_allowlist)),
        ]
    )
    return _cached_chat_stream_service(settings_key)


def clear_chat_stream_service_cache() -> None:
    _cached_chat_stream_service.cache_clear()
