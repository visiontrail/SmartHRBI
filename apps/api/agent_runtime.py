from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from .agent_guardrails import AgentGuardrailContext, AgentGuardrailError, AgentGuardrails
from .agent_logging import format_agent_debug_blocks
from .agent_prompting import build_agent_system_prompt
from .audit import get_audit_logger
from .chart_strategy import ChartStrategyRouter
from .config import get_settings
from .llm_anthropic import (
    AnthropicAgentClient,
    AnthropicLLMError,
    AnthropicLLMResponse,
    AnthropicToolCall,
    build_anthropic_content_blocks,
)
from .tool_calling import ToolCall, ToolCallRequest, ToolCallResponse, get_tool_calling_service

logger = logging.getLogger("smarthrbi.agent")

# ---------------------------------------------------------------------------
# Tool definitions (converted to Anthropic format by the LLM client)
# ---------------------------------------------------------------------------

AGENT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List all dataset tables available in the current project.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": (
                "Inspect a table's column names, types, and sample rows. "
                "Always call this before writing SQL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name to inspect"},
                    "sample_limit": {
                        "type": "integer",
                        "description": "Number of sample rows to return (1-50, default 8)",
                    },
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_rows",
            "description": (
                "Fetch sample rows from a table to inspect actual data values. "
                "Use this to see real values in categorical columns before filtering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "limit": {"type": "integer", "description": "Number of rows (1-50, default 8)"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_distinct_values",
            "description": (
                "Return the distinct values and their frequency for a categorical column. "
                "Call this before applying any filter on a column when you are unsure of the "
                "exact stored values (e.g. the user says 'HR' but the data might store '人力资源')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "description": "Column name"},
                    "table": {"type": "string", "description": "Table name (optional, defaults to active dataset)"},
                    "limit": {"type": "integer", "description": "Max distinct values to return (default 20)"},
                },
                "required": ["field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metric_catalog",
            "description": "Return the list of pre-defined semantic metrics available in the catalog.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_semantic_query",
            "description": (
                "Execute a semantic/metric query using the catalog. "
                "Prefer this over raw SQL when a matching metric exists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "Metric name from catalog"},
                    "intent": {"type": "string", "description": "Natural language intent if metric name unknown"},
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Columns to group by",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string"},
                                "value": {},
                            },
                        },
                        "description": "Filter conditions",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_readonly_sql",
            "description": (
                "Execute a readonly DuckDB SQL query against the dataset. "
                "Use only when the semantic catalog cannot satisfy the request. "
                "Row-level security and column redaction are automatically applied."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SELECT statement to execute"},
                    "max_rows": {
                        "type": "integer",
                        "description": "Maximum rows to return (default 200)",
                    },
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_view",
            "description": "Save the current chart/SQL as a named view (only when user explicitly requests it).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "chart_spec": {"type": "object"},
                    "sql": {"type": "string"},
                    "conversation_id": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Submit the final structured answer when you have gathered enough data. "
                "This produces the chart or table that the user will see.\n\n"
                "## Chart type guide\n"
                "- bar: compare categories side-by-side.\n"
                "- line: show trends over time.\n"
                "- pie: show proportion / share of a whole.\n"
                "- area: like line but filled, good for volume over time.\n"
                "- scatter: show correlation between two numeric variables.\n"
                "- radar: compare multiple dimensions for a few items.\n"
                "- treemap: show hierarchical part-of-whole; each rectangle = one item, "
                "grouped by a category dimension. Set x_key to the grouping dimension "
                "(e.g. department), name_key to the label shown inside each box "
                "(e.g. employee name), and y_key to the size metric (or omit for equal sizing).\n"
                "- funnel: show conversion / pipeline stages.\n"
                "- radialBar: circular bar chart for ranking/comparison.\n"
                "- composed: overlay bar + line + area on the same axes.\n"
                "- heatmap: 2D grid coloured by intensity (uses ECharts).\n"
                "- gauge: single KPI dial (uses ECharts).\n"
                "- sankey: flow diagram between stages (uses ECharts).\n"
                "- sunburst: nested ring hierarchy (uses ECharts).\n"
                "- boxplot: statistical distribution (uses ECharts).\n"
                "- graph: network / relationship diagram (uses ECharts).\n"
                "- table: structured row/column table.\n"
                "- single_value: display one big number.\n"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": [
                            "bar", "line", "pie", "area", "scatter", "radar",
                            "treemap", "funnel", "radialBar", "composed",
                            "heatmap", "gauge", "sankey", "sunburst",
                            "boxplot", "graph",
                            "table", "single_value",
                        ],
                        "description": "Chart type for visualization",
                    },
                    "title": {"type": "string", "description": "Human-readable title"},
                    "x_key": {"type": "string", "description": "Dimension / grouping column name"},
                    "y_key": {"type": "string", "description": "Metric / size column name"},
                    "name_key": {
                        "type": "string",
                        "description": (
                            "Label column name shown inside each element "
                            "(e.g. employee name in treemap boxes). Only used for treemap/graph."
                        ),
                    },
                    "series_key": {
                        "type": "string",
                        "description": "Series column name for multi-series charts, or null",
                    },
                    "metric_name": {"type": "string", "description": "Short internal metric name"},
                    "rows": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of data objects for the chart",
                    },
                    "conclusion": {"type": "string", "description": "1-2 sentence insight from the data"},
                    "scope": {"type": "string", "description": "What the query covers, filters applied"},
                    "anomalies": {
                        "type": "string",
                        "description": "Empty result reason, access restriction, or 'none'",
                    },
                },
                "required": ["chart_type", "title", "rows", "conclusion"],
            },
        },
    },
]

GROUNDING_TOOL_NAMES = frozenset(
    {
        "list_tables",
        "describe_table",
        "sample_rows",
        "get_metric_catalog",
        "run_semantic_query",
        "execute_readonly_sql",
        "get_distinct_values",
        "query_metrics",
        "describe_dataset",
    }
)

TOOL_RESULT_RECOVERY_PRIORITY = (
    "execute_readonly_sql",
    "run_semantic_query",
    "get_distinct_values",
    "sample_rows",
    "describe_table",
    "list_tables",
)

SUBMIT_ANSWER_TOOL_NAME = "submit_answer"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class AgentRuntimeError(Exception):
    def __init__(self, *, code: str, message: str, should_fallback: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.should_fallback = should_fallback

    def to_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "should_fallback": self.should_fallback,
        }


@dataclass(slots=True)
class AgentRequest:
    conversation_id: str
    request_id: str
    user_id: str
    project_id: str
    dataset_table: str
    message: str
    role: str
    department: str | None
    clearance: int


@dataclass(slots=True)
class AgentSessionState:
    conversation_id: str
    agent_session_id: str
    history: list[dict[str, Any]] = field(default_factory=list)
    last_result: dict[str, Any] | None = None
    last_spec: dict[str, Any] | None = None
    last_tool_trace: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _utc_now())
    updated_at: str = field(default_factory=lambda: _utc_now())
    turn_count: int = 0
    runtime_backend: str = "anthropic-agent-loop"

    def to_record(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "agent_session_id": self.agent_session_id,
            "history": self.history,
            "last_result": self.last_result,
            "last_spec": self.last_spec,
            "last_tool_trace": self.last_tool_trace,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
            "runtime_backend": self.runtime_backend,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "AgentSessionState":
        return cls(
            conversation_id=str(record.get("conversation_id") or ""),
            agent_session_id=str(record.get("agent_session_id") or uuid.uuid4().hex),
            history=list(record.get("history") or []),
            last_result=record.get("last_result") if isinstance(record.get("last_result"), dict) else None,
            last_spec=record.get("last_spec") if isinstance(record.get("last_spec"), dict) else None,
            last_tool_trace=list(record.get("last_tool_trace") or []),
            created_at=str(record.get("created_at") or _utc_now()),
            updated_at=str(record.get("updated_at") or _utc_now()),
            turn_count=int(record.get("turn_count") or 0),
            runtime_backend=str(record.get("runtime_backend") or "anthropic-agent-loop"),
        )


@dataclass(slots=True)
class AgentTurnResult:
    conversation_id: str
    request_id: str
    agent_session_id: str
    events: list[tuple[str, dict[str, Any]]]
    tool_trace: list[dict[str, Any]]
    final_text: str
    final_status: str
    spec: dict[str, Any]
    ai_state: dict[str, Any]


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


class AgentSessionStore:
    def __init__(self, *, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_schema()

    def load(self, conversation_id: str) -> AgentSessionState | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM agent_sessions WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["state_json"]))
        if not isinstance(payload, dict):
            return None
        return AgentSessionState.from_record(payload)

    def save(self, state: AgentSessionState) -> None:
        state.updated_at = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (
                    conversation_id,
                    agent_session_id,
                    state_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    agent_session_id = excluded.agent_session_id,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    state.conversation_id,
                    state.agent_session_id,
                    json.dumps(
                        state.to_record(),
                        ensure_ascii=False,
                        default=str,
                        separators=(",", ":"),
                    ),
                    state.created_at,
                    state.updated_at,
                ),
            )
            conn.commit()

    def clear(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM agent_sessions")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    conversation_id TEXT PRIMARY KEY,
                    agent_session_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Agent runtime — Anthropic SDK agent loop
# ---------------------------------------------------------------------------


class AgentRuntime:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.guardrails = AgentGuardrails()
        self.tool_service = get_tool_calling_service()
        self.router = ChartStrategyRouter()
        self.system_prompt = build_agent_system_prompt()
        self._store = AgentSessionStore(
            db_path=(settings.upload_dir / "state" / "agent_sessions.sqlite3").resolve()
        )
        self._hot_sessions: dict[str, AgentSessionState] = {}
        self._lock = Lock()
        self._llm = AnthropicAgentClient(
            base_url=settings.model_provider_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            tool_definitions=AGENT_TOOL_DEFINITIONS,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_turn(self, request: AgentRequest) -> AgentTurnResult:
        started = time.perf_counter()
        session = self._load_session(request.conversation_id)
        guard_context = AgentGuardrailContext(
            role=request.role,
            user_id=request.user_id,
            project_id=request.project_id,
        )
        self.guardrails.validate_user_message(message=request.message, context=guard_context)
        resolved_dataset_table = self._resolve_request_dataset_table(request=request)
        if resolved_dataset_table and resolved_dataset_table != request.dataset_table:
            logger.warning(
                "agent_dataset_table_fallback conversation_id=%s request_id=%s requested=%s resolved=%s",
                request.conversation_id,
                request.request_id,
                request.dataset_table,
                resolved_dataset_table,
            )
            request.dataset_table = resolved_dataset_table

        tool_trace: list[dict[str, Any]] = []
        events: list[tuple[str, dict[str, Any]]] = []

        system_text = self._build_system_text(request=request, session=session)
        messages = self._build_initial_messages(request=request, session=session)

        logger.info(
            "agent_turn_start_debug conversation_id=%s request_id=%s agent_session_id=%s\n%s",
            request.conversation_id,
            request.request_id,
            session.agent_session_id,
            format_agent_debug_blocks(
                ai_input={
                    "conversation_id": request.conversation_id,
                    "request_id": request.request_id,
                    "agent_session_id": session.agent_session_id,
                    "dataset_table": request.dataset_table,
                    "message": request.message,
                    "messages": messages,
                },
            ),
        )

        # ---------- Anthropic agent loop ----------
        max_steps = self.settings.agent_max_tool_steps
        final_answer: dict[str, Any] | None = None

        for step in range(1, max_steps + 1):
            logger.info(
                "agent_loop_step conversation_id=%s request_id=%s step=%s/%s",
                request.conversation_id,
                request.request_id,
                step,
                max_steps,
            )

            try:
                llm_response = self._llm.chat(
                    system=system_text,
                    messages=messages,
                    conversation_id=request.conversation_id,
                    step=step,
                )
            except AnthropicLLMError as exc:
                raise AgentRuntimeError(
                    code="AGENT_LLM_FAILED",
                    message=f"LLM call failed at step {step}: {exc.message}",
                    should_fallback=False,
                ) from exc

            # Use model's own thinking/reasoning for planning events
            if step == 1:
                events.extend(
                    self._extract_planning_events(
                        llm_response=llm_response,
                        request=request,
                        session=session,
                    )
                )

            logger.info(
                "agent_loop_step_debug conversation_id=%s request_id=%s step=%s\n%s",
                request.conversation_id,
                request.request_id,
                step,
                format_agent_debug_blocks(
                    ai_output={
                        "conversation_id": request.conversation_id,
                        "request_id": request.request_id,
                        "step": step,
                        "stop_reason": llm_response.stop_reason,
                    },
                    thinking=llm_response.thinking or llm_response.content,
                ),
            )

            # No tool calls → model produced a text-only final response
            if not llm_response.tool_calls:
                candidate_answer = _parse_final_answer(llm_response.content)
                if candidate_answer is not None:
                    final_answer = candidate_answer
                break

            # Check if the model submitted a structured answer via submit_answer
            submit_call = next(
                (tc for tc in llm_response.tool_calls if tc.tool_name == SUBMIT_ANSWER_TOOL_NAME),
                None,
            )

            # Build assistant message (OpenAI format) and add to history
            assistant_msg = build_anthropic_content_blocks(llm_response)
            messages.append(assistant_msg)

            # Execute tool calls (submit_answer is acknowledged, not executed)
            for tc in llm_response.tool_calls:
                if tc.tool_name == SUBMIT_ANSWER_TOOL_NAME:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.call_id,
                        "content": '{"status": "accepted"}',
                    })
                    continue

                tool_result = self._execute_tool_call(
                    tool_call=tc,
                    request=request,
                    session=session,
                    tool_trace=tool_trace,
                    events=events,
                    step=step,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.call_id,
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                })

            if submit_call:
                final_answer = submit_call.arguments
                break

        # ------ Build chart spec from final answer ------
        if final_answer is not None:
            spec = self._spec_from_final_answer(final_answer, request=request)
            final_text = _compose_final_text(final_answer)
            result_payload = final_answer
        else:
            spec = self._empty_spec(request=request)
            has_grounding = _has_grounding_tool_observation(tool_trace)
            if has_grounding:
                recovered_answer = _recover_final_answer_from_tool_trace(
                    tool_trace=tool_trace,
                    request_message=request.message,
                )
                if recovered_answer is not None:
                    spec = self._spec_from_final_answer(recovered_answer, request=request)
                    final_text = _compose_final_text(recovered_answer)
                    result_payload = recovered_answer
                else:
                    final_text = "Agent collected tool observations but did not return a usable structured answer."
                    result_payload = {"rows": [], "conclusion": "", "anomalies": "final_answer_parse_failed"}
            else:
                final_text = "Agent stopped to avoid ungrounded output because no successful BI tool observation was produced."
                result_payload = {"rows": [], "conclusion": "", "anomalies": "no_grounded_tool_observation"}

        return self._finalize_turn(
            request=request,
            session=session,
            events=events,
            tool_trace=tool_trace,
            spec=spec,
            final_text=final_text,
            result_payload=result_payload,
            started=started,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def clear_runtime_state(self, *, clear_persisted: bool = False) -> None:
        with self._lock:
            self._hot_sessions.clear()
        if clear_persisted:
            self._store.clear()

    def get_persisted_session(self, conversation_id: str) -> AgentSessionState | None:
        return self._store.load(conversation_id)

    def _load_session(self, conversation_id: str) -> AgentSessionState:
        with self._lock:
            session = self._hot_sessions.get(conversation_id)
        if session is not None:
            return session

        stored = self._store.load(conversation_id)
        if stored is not None:
            with self._lock:
                self._hot_sessions[conversation_id] = stored
            return stored

        session = AgentSessionState(
            conversation_id=conversation_id,
            agent_session_id=uuid.uuid4().hex,
            runtime_backend="anthropic-agent-loop",
        )
        with self._lock:
            self._hot_sessions[conversation_id] = session
        self._store.save(session)
        return session

    def _resolve_request_dataset_table(self, *, request: AgentRequest) -> str:
        try:
            all_tables = self.tool_service.dataset_service.list_tables(
                user_id=request.user_id,
                project_id=request.project_id,
            )
        except Exception:
            return request.dataset_table

        if not all_tables:
            return request.dataset_table

        canonical = self._match_table_name(request.dataset_table, all_tables)
        if canonical is not None:
            return canonical

        if len(all_tables) == 1:
            return all_tables[0]
        return request.dataset_table

    @staticmethod
    def _match_table_name(table_name: str, candidates: list[str]) -> str | None:
        target = table_name.strip().lower()
        if not target:
            return None
        candidate_map = {item.lower(): item for item in candidates}
        return candidate_map.get(target)

    def _build_system_text(
        self,
        *,
        request: AgentRequest,
        session: AgentSessionState,
    ) -> str:
        """Compose the system prompt with per-request context.

        The Anthropic Messages API takes system as a separate parameter,
        so context that varies per request is appended here rather than
        injected as extra messages.
        """
        parts = [self.system_prompt]

        try:
            all_tables = self.tool_service.dataset_service.list_tables(
                user_id=request.user_id, project_id=request.project_id
            )
        except Exception:
            all_tables = [request.dataset_table]

        if len(all_tables) > 1:
            other_tables = [t for t in all_tables if t != request.dataset_table]
            tables_hint = (
                f"Active dataset table: `{request.dataset_table}`. "
                f"Other tables in this session: {', '.join(f'`{t}`' for t in other_tables)}. "
                "You may JOIN across these tables in execute_readonly_sql when answering cross-table questions."
            )
        else:
            tables_hint = f"Active dataset table: `{request.dataset_table}`."

        context_hint = (
            tables_hint
            + f" User role: {request.role}."
            + " Row-level security is enforced automatically on all queries."
        )
        parts.append(context_hint)

        if session.last_result and isinstance(session.last_result, dict):
            prior_summary = json.dumps(session.last_result, ensure_ascii=False, default=str)
            if len(prior_summary) > 2000:
                prior_summary = prior_summary[:2000] + "..."
            parts.append(
                f"Previous turn result is available for context: {prior_summary}"
            )

        return "\n\n".join(parts)

    def _build_initial_messages(
        self,
        *,
        request: AgentRequest,
        session: AgentSessionState,
    ) -> list[dict[str, Any]]:
        """Build the Anthropic-format message list (user/assistant only; no system role)."""
        messages: list[dict[str, Any]] = []

        for item in session.history[-10:]:
            role = str(item.get("role") or "")
            content = item.get("content") or ""
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": str(content)})

        messages.append({"role": "user", "content": request.message})
        return messages

    def _extract_planning_events(
        self,
        *,
        llm_response: AnthropicLLMResponse,
        request: AgentRequest,
        session: AgentSessionState,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Build planning events from the model's own thinking/reasoning."""
        planning_text = llm_response.thinking or llm_response.content or ""
        if not planning_text.strip():
            planning_text = f"Analyzing request for dataset `{request.dataset_table}`."

        payload = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "text": planning_text,
        }
        compatibility = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "text": planning_text,
            "compatibility_mirror": True,
        }
        return [("planning", payload), ("reasoning", compatibility)]

    def _execute_tool_call(
        self,
        *,
        tool_call: AnthropicToolCall,
        request: AgentRequest,
        session: AgentSessionState,
        tool_trace: list[dict[str, Any]],
        events: list[tuple[str, dict[str, Any]]],
        step: int,
    ) -> dict[str, Any]:
        tool_name = tool_call.tool_name
        arguments = tool_call.arguments

        # Guardrail check
        guard_context = AgentGuardrailContext(
            role=request.role,
            user_id=request.user_id,
            project_id=request.project_id,
        )
        try:
            self.guardrails.validate_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                context=guard_context,
            )
        except AgentGuardrailError as exc:
            logger.warning(
                "agent_tool_blocked conversation_id=%s step=%s tool=%s code=%s",
                request.conversation_id,
                step,
                tool_name,
                exc.code,
            )
            logger.warning(
                "agent_tool_blocked_debug conversation_id=%s request_id=%s step=%s tool=%s\n%s",
                request.conversation_id,
                request.request_id,
                step,
                tool_name,
                format_agent_debug_blocks(
                    tool_trace={
                        "conversation_id": request.conversation_id,
                        "request_id": request.request_id,
                        "step": step,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "error": {"code": exc.code, "message": exc.message},
                    }
                ),
            )
            # Return the error as a tool result so the LLM can reason about it
            return {"error": exc.code, "message": exc.message}

        tool_step = len(tool_trace) + 1
        tool_use_payload = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "tool_name": tool_name,
            "step": tool_step,
            "arguments": arguments,
        }
        events.append(("tool_use", tool_use_payload))
        tool_trace.append({"event": "tool_use", **tool_use_payload})
        get_audit_logger().log(
            event_type="agent",
            action="agent_pre_tool_use",
            status="success",
            user_id=request.user_id,
            project_id=request.project_id,
            detail={"tool_name": tool_name, "step": tool_step, "conversation_id": request.conversation_id},
        )

        response = self.tool_service.invoke(
            ToolCallRequest(
                conversation_id=request.conversation_id,
                request_id=request.request_id,
                idempotency_key=f"{request.request_id}:{tool_name}:{tool_step}",
                user_id=request.user_id,
                project_id=request.project_id,
                dataset_table=request.dataset_table,
                role=request.role,
                department=request.department,
                clearance=request.clearance,
                emit_debug_blocks=False,
                tool=ToolCall(name=tool_name, arguments=arguments),
            )
        )

        result_data = response.result if response.status == "success" else {"error": response.error}

        tool_result_payload = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "tool_name": tool_name,
            "step": tool_step,
            "status": response.status,
            "result": result_data,
            "error": response.error,
            "from_cache": response.from_cache,
        }
        events.append(("tool_result", tool_result_payload))
        events.append(
            (
                "tool",
                {
                    "conversation_id": request.conversation_id,
                    "request_id": request.request_id,
                    "tool_name": tool_name,
                    "status": response.status,
                    "result": result_data,
                    "error": response.error,
                    "compatibility_mirror": True,
                },
            )
        )
        tool_trace.append({"event": "tool_result", **tool_result_payload})
        logger.info(
            "agent_tool_trace_debug conversation_id=%s request_id=%s step=%s tool_name=%s\n%s",
            request.conversation_id,
            request.request_id,
            tool_step,
            tool_name,
            format_agent_debug_blocks(
                tool_result={
                    "conversation_id": request.conversation_id,
                    "request_id": request.request_id,
                    "agent_session_id": session.agent_session_id,
                    "step": tool_step,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "status": response.status,
                    "result": result_data,
                    "error": response.error,
                    "from_cache": response.from_cache,
                }
            ),
        )
        get_audit_logger().log(
            event_type="agent",
            action="agent_post_tool_use",
            status="success" if response.status == "success" else "failed",
            severity="INFO" if response.status == "success" else "ALERT",
            user_id=request.user_id,
            project_id=request.project_id,
            detail={"tool_name": tool_name, "step": tool_step, "conversation_id": request.conversation_id},
        )

        return result_data or {}

    # Chart types that Recharts can render natively
    RECHARTS_TYPES = frozenset({
        "bar", "line", "pie", "area", "scatter", "radar",
        "treemap", "funnel", "radialBar", "composed",
        "table", "single_value", "note", "empty",
    })

    # Chart types that must be routed to ECharts (need config.option)
    ECHARTS_ONLY_TYPES = frozenset({
        "heatmap", "gauge", "sankey", "sunburst",
        "boxplot", "candlestick", "graph", "map", "parallel", "wordCloud",
    })

    # All valid chart types (union of both)
    ALL_CHART_TYPES = RECHARTS_TYPES | ECHARTS_ONLY_TYPES

    def _spec_from_final_answer(
        self,
        answer: dict[str, Any],
        *,
        request: AgentRequest,
    ) -> dict[str, Any]:
        rows = list(answer.get("rows") or [])
        chart_type = str(answer.get("chart_type") or "bar")
        if chart_type not in self.ALL_CHART_TYPES:
            chart_type = "bar"
        if not rows:
            chart_type = "empty"

        x_key = str(answer.get("x_key") or _guess_dimension_key(rows, fallback="dimension"))
        y_key = str(answer.get("y_key") or _guess_metric_key(rows, fallback="metric_value"))
        name_key = answer.get("name_key") or None
        series_key = answer.get("series_key") or None
        metric_name = str(answer.get("metric_name") or "metric")
        title = str(answer.get("title") or request.message[:60])

        # Decide engine: ECharts-only types always use echarts; multi-series line also
        if chart_type in self.ECHARTS_ONLY_TYPES:
            engine = "echarts"
        elif chart_type == "line" and series_key:
            engine = "echarts"
        else:
            engine = "recharts"

        if engine == "echarts":
            option = _build_echarts_option(
                chart_type=chart_type,
                rows=rows,
                x_key=x_key,
                y_key=y_key,
                name_key=str(name_key) if name_key else None,
                series_key=str(series_key) if series_key else None,
                title=title,
                metric_name=metric_name,
            )
            # Normalise echarts chart_type to a valid catalog value
            echarts_catalog = {
                "bar", "line", "pie", "scatter", "treemap", "heatmap",
                "radar", "funnel", "gauge", "sankey", "sunburst",
                "boxplot", "candlestick", "graph", "map", "parallel", "wordCloud",
            }
            echarts_ct = chart_type if chart_type in echarts_catalog else "bar"
            config: dict[str, Any] = {"option": option}
        else:
            echarts_ct = chart_type  # unused, but keeps typing simple
            config = {"xKey": x_key, "yKey": y_key, "metricName": metric_name}
            if name_key:
                config["nameKey"] = name_key
            if series_key:
                config["seriesKey"] = series_key

        final_chart_type = echarts_ct if engine == "echarts" else chart_type

        return {
            "engine": engine,
            "chart_type": final_chart_type,
            "title": title,
            "data": rows,
            "config": config,
            "route": {
                "complexity_score": len(rows) + (3 if series_key else 1),
                "threshold": self.router.COMPLEXITY_THRESHOLD,
                "reasons": ["llm_react_loop"],
                "selected_engine": engine,
            },
            "meta": {"intent": request.message, "generated_by": "anthropic_agent_loop"},
        }

    def _empty_spec(self, *, request: AgentRequest) -> dict[str, Any]:
        return {
            "engine": "recharts",
            "chart_type": "empty",
            "title": "No data",
            "data": [],
            "config": {},
            "route": {
                "complexity_score": 0,
                "threshold": self.router.COMPLEXITY_THRESHOLD,
                "reasons": ["agent_no_answer"],
                "selected_engine": "recharts",
            },
            "meta": {"intent": request.message, "generated_by": "anthropic_agent_loop"},
        }

    def _finalize_turn(
        self,
        *,
        request: AgentRequest,
        session: AgentSessionState,
        events: list[tuple[str, dict[str, Any]]],
        tool_trace: list[dict[str, Any]],
        spec: dict[str, Any],
        final_text: str,
        result_payload: dict[str, Any],
        started: float,
    ) -> AgentTurnResult:
        events.append(
            (
                "spec",
                {
                    "conversation_id": request.conversation_id,
                    "request_id": request.request_id,
                    "agent_session_id": session.agent_session_id,
                    "spec": spec,
                },
            )
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        final_payload = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "status": "completed",
            "text": final_text,
            "engine": "agent_primary",
            "duration_ms": duration_ms,
            "tool_steps": len([item for item in tool_trace if item.get("event") == "tool_use"]),
        }
        events.append(("final", final_payload))

        session.turn_count += 1
        session.history.append({"role": "user", "content": request.message})
        session.history.append({"role": "assistant", "content": final_text})
        session.last_result = result_payload
        session.last_spec = spec
        session.last_tool_trace = tool_trace
        self._store.save(session)
        with self._lock:
            self._hot_sessions[request.conversation_id] = session

        ai_state = {
            "conversation_id": request.conversation_id,
            "agent_session_id": session.agent_session_id,
            "tool_trace": tool_trace,
            "latest_result": result_payload,
            "latest_spec": spec,
            "turn_count": session.turn_count,
            "runtime_backend": session.runtime_backend,
        }
        tool_use_trace = [item for item in tool_trace if item.get("event") == "tool_use"]
        tool_result_trace = [item for item in tool_trace if item.get("event") == "tool_result"]
        logger.info(
            "agent_turn_final_debug conversation_id=%s request_id=%s agent_session_id=%s\n%s",
            request.conversation_id,
            request.request_id,
            session.agent_session_id,
            format_agent_debug_blocks(
                ai_output={
                    "conversation_id": request.conversation_id,
                    "request_id": request.request_id,
                    "agent_session_id": session.agent_session_id,
                    "status": "completed",
                    "final_text": final_text,
                    "result_payload": result_payload,
                    "spec": spec,
                },
                tool_trace=tool_use_trace,
                tool_result=tool_result_trace,
            ),
        )
        return AgentTurnResult(
            conversation_id=request.conversation_id,
            request_id=request.request_id,
            agent_session_id=session.agent_session_id,
            events=events,
            tool_trace=tool_trace,
            final_text=final_text,
            final_status="completed",
            spec=spec,
            ai_state=ai_state,
        )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@lru_cache(maxsize=2)
def _cached_agent_runtime(settings_key: str) -> AgentRuntime:
    _ = settings_key
    return AgentRuntime()


def get_agent_runtime() -> AgentRuntime:
    settings = get_settings()
    key = "|".join(
        [
            str(settings.upload_dir.resolve()),
            settings.chat_engine,
            str(settings.agent_max_tool_steps),
            str(settings.agent_max_sql_rows),
            str(settings.agent_max_sql_scan_rows),
        ]
    )
    return _cached_agent_runtime(key)


def clear_agent_runtime_cache() -> None:
    _cached_agent_runtime.cache_clear()


# ---------------------------------------------------------------------------
# LLM message helpers
# ---------------------------------------------------------------------------



def _parse_final_answer(content: str) -> dict[str, Any] | None:
    """Try to extract a structured JSON final answer from LLM content."""
    text = content.strip()
    if not text:
        return None

    # Direct JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and ("rows" in parsed or "chart_type" in parsed):
            return parsed
    except json.JSONDecodeError:
        pass

    # JSON inside a code block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict) and ("rows" in parsed or "chart_type" in parsed):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def _has_grounding_tool_observation(tool_trace: list[dict[str, Any]]) -> bool:
    for item in tool_trace:
        if item.get("event") != "tool_result":
            continue
        if item.get("status") != "success":
            continue
        if str(item.get("tool_name") or "") in GROUNDING_TOOL_NAMES:
            return True
    return False


def _recover_final_answer_from_tool_trace(
    *,
    tool_trace: list[dict[str, Any]],
    request_message: str,
) -> dict[str, Any] | None:
    successful_results = [
        item
        for item in tool_trace
        if item.get("event") == "tool_result"
        and item.get("status") == "success"
        and str(item.get("tool_name") or "") in GROUNDING_TOOL_NAMES
    ]
    if not successful_results:
        return None

    non_empty = _recover_final_answer_from_results(
        successful_results=successful_results,
        request_message=request_message,
        require_non_empty_rows=True,
    )
    if non_empty is not None:
        return non_empty

    return _recover_final_answer_from_results(
        successful_results=successful_results,
        request_message=request_message,
        require_non_empty_rows=False,
    )


def _recover_final_answer_from_results(
    *,
    successful_results: list[dict[str, Any]],
    request_message: str,
    require_non_empty_rows: bool,
) -> dict[str, Any] | None:
    for tool_name in TOOL_RESULT_RECOVERY_PRIORITY:
        for item in reversed(successful_results):
            current_tool = str(item.get("tool_name") or "")
            if current_tool != tool_name:
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            rows = _extract_rows_from_tool_result(tool_name=current_tool, result=result)
            if rows is None:
                continue
            if require_non_empty_rows and not rows:
                continue

            dimension_key, metric_key = _guess_dimension_and_metric_keys(rows)
            chart_type = "table"
            if rows and dimension_key and metric_key:
                chart_type = "bar"
            elif len(rows) == 1 and metric_key and not dimension_key:
                chart_type = "single_value"

            metric_name = str(result.get("metric") or metric_key or current_tool or "metric")
            return {
                "chart_type": chart_type,
                "title": _title_from_tool_result(
                    tool_name=current_tool,
                    result=result,
                    request_message=request_message,
                ),
                "x_key": dimension_key or "dimension",
                "y_key": metric_key or "metric_value",
                "series_key": None,
                "metric_name": metric_name,
                "rows": rows,
                "conclusion": _conclusion_from_tool_rows(
                    rows=rows,
                    dimension_key=dimension_key,
                    metric_key=metric_key,
                ),
                "scope": _scope_from_tool_result(tool_name=current_tool, result=result),
                "anomalies": "agent_auto_composed_from_tool_result",
            }
    return None


def _extract_rows_from_tool_result(*, tool_name: str, result: dict[str, Any]) -> list[dict[str, Any]] | None:
    if tool_name in {"execute_readonly_sql", "run_semantic_query", "sample_rows"}:
        return _coerce_rows(result.get("rows"))
    if tool_name == "get_distinct_values":
        return _coerce_rows(result.get("values"))
    if tool_name == "describe_table":
        return _coerce_rows(result.get("sample_rows"))
    if tool_name == "list_tables":
        tables = result.get("tables")
        if isinstance(tables, list):
            return [{"table": str(item)} for item in tables]
        return []
    return None


def _coerce_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _guess_dimension_and_metric_keys(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not rows:
        return None, None

    first_row = rows[0]
    if not isinstance(first_row, dict) or not first_row:
        return None, None

    keys = [str(key) for key in first_row.keys()]
    metric_candidates = ("metric_value", "frequency", "count", "employee_count")
    metric_key = next((key for key in metric_candidates if key in first_row and _is_number(first_row.get(key))), None)
    if metric_key is None:
        metric_key = next((key for key in keys if _is_number(first_row.get(key))), None)

    dimension_key = next((key for key in keys if key != metric_key and not _is_number(first_row.get(key))), None)
    return dimension_key, metric_key


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _title_from_tool_result(*, tool_name: str, result: dict[str, Any], request_message: str) -> str:
    if tool_name == "execute_readonly_sql":
        return "SQL 查询结果"
    if tool_name == "run_semantic_query":
        metric = str(result.get("metric") or "").strip()
        return f"{metric} 查询结果" if metric else "语义查询结果"
    if tool_name == "get_distinct_values":
        field = str(result.get("field") or "字段").strip() or "字段"
        return f"{field} 值分布"
    if tool_name == "sample_rows":
        table = str(result.get("table") or "").strip()
        return f"{table} 样本记录" if table else "样本记录"
    if tool_name == "describe_table":
        table = str(result.get("table") or "").strip()
        return f"{table} 表结构与样本" if table else "表结构与样本"
    if tool_name == "list_tables":
        return "可用数据表"
    trimmed = request_message.strip()
    return trimmed[:60] if trimmed else "查询结果"


def _scope_from_tool_result(*, tool_name: str, result: dict[str, Any]) -> str:
    row_count = result.get("row_count")
    if isinstance(row_count, int):
        return f"来源工具: {tool_name}，返回 {row_count} 行。"
    return f"来源工具: {tool_name}。"


def _conclusion_from_tool_rows(
    *,
    rows: list[dict[str, Any]],
    dimension_key: str | None,
    metric_key: str | None,
) -> str:
    if not rows:
        return "已基于成功工具结果自动生成答案，但当前结果为空。"

    if dimension_key and metric_key:
        ranked = [row for row in rows if _is_number(row.get(metric_key))]
        if ranked:
            top_row = max(ranked, key=lambda row: float(row.get(metric_key) or 0))
            return (
                "已基于成功工具结果自动生成答案。"
                f" {dimension_key}={top_row.get(dimension_key)} 的 {metric_key} 最高，为 {top_row.get(metric_key)}。"
            )
        return f"已基于成功工具结果自动生成答案，共返回 {len(rows)} 行。"

    if metric_key:
        numeric_values = [float(row.get(metric_key) or 0) for row in rows if _is_number(row.get(metric_key))]
        if numeric_values:
            return (
                "已基于成功工具结果自动生成答案。"
                f" 共返回 {len(rows)} 行，{metric_key} 合计 {round(sum(numeric_values), 2)}。"
            )

    return f"已基于成功工具结果自动生成答案，共返回 {len(rows)} 行。"




# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------


def _compose_final_text(answer: dict[str, Any]) -> str:
    title = str(answer.get("title") or "Result")
    rows = list(answer.get("rows") or [])
    conclusion = str(answer.get("conclusion") or "")
    scope = str(answer.get("scope") or "")
    anomalies = str(answer.get("anomalies") or "")

    if not rows:
        return (
            f"{title} 没有返回可展示数据。"
            f"{('口径: ' + scope) if scope else ''} "
            f"{('异常说明: ' + anomalies) if anomalies else '可能原因: 过滤条件、权限范围或源数据分布导致结果为空。'}"
        ).strip()

    parts = [f"{title} 已生成，共 {len(rows)} 行。"]
    if conclusion:
        parts.append(f"结论: {conclusion}")
    if scope:
        parts.append(f"口径: {scope}")
    if anomalies:
        parts.append(f"异常说明: {anomalies}")
    return " ".join(parts)


def _build_echarts_option(
    *,
    chart_type: str,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    name_key: str | None,
    series_key: str | None,
    title: str,
    metric_name: str,
) -> dict[str, Any]:
    """Build a complete ECharts option dict from flat rows."""

    if chart_type == "treemap":
        return _echarts_treemap_option(rows=rows, x_key=x_key, y_key=y_key, name_key=name_key, title=title)
    if chart_type == "heatmap":
        return _echarts_heatmap_option(rows=rows, x_key=x_key, y_key=y_key, series_key=series_key)
    if chart_type == "radar":
        return _echarts_radar_option(rows=rows, x_key=x_key, y_key=y_key, metric_name=metric_name)
    if chart_type == "funnel":
        return _echarts_funnel_option(rows=rows, x_key=x_key, y_key=y_key)
    if chart_type == "gauge":
        return _echarts_gauge_option(rows=rows, y_key=y_key, title=title)
    if chart_type == "sankey":
        return _echarts_sankey_option(rows=rows)
    if chart_type == "sunburst":
        return _echarts_sunburst_option(rows=rows, x_key=x_key, y_key=y_key)
    if chart_type == "boxplot":
        return _echarts_boxplot_option(rows=rows, x_key=x_key, y_key=y_key)
    if chart_type == "graph":
        return _echarts_graph_option(rows=rows, x_key=x_key, y_key=y_key)
    if chart_type == "pie":
        return _echarts_pie_option(rows=rows, x_key=x_key, y_key=y_key)
    if chart_type == "scatter":
        return _echarts_scatter_option(rows=rows, x_key=x_key, y_key=y_key)

    # Default: category axis bar/line
    return _echarts_cartesian_option(
        rows=rows, x_key=x_key, y_key=y_key,
        series_key=series_key, series_type=chart_type if chart_type in {"line", "bar"} else "bar",
        metric_name=metric_name,
    )


def _echarts_cartesian_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    series_key: str | None,
    series_type: str,
    metric_name: str,
) -> dict[str, Any]:
    if series_key:
        series_groups: dict[str, list] = {}
        categories_set: list[str] = []
        for row in rows:
            cat = str(row.get(x_key, ""))
            if cat not in categories_set:
                categories_set.append(cat)
            sg = str(row.get(series_key, ""))
            series_groups.setdefault(sg, {})[cat] = row.get(y_key, 0)

        series_list = []
        for sg_name, cat_map in series_groups.items():
            series_list.append({
                "name": sg_name,
                "type": series_type,
                "smooth": True,
                "data": [cat_map.get(c, 0) for c in categories_set],
            })
        return {
            "tooltip": {"trigger": "axis"},
            "legend": {},
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            "xAxis": {"type": "category", "data": categories_set},
            "yAxis": {"type": "value"},
            "series": series_list,
        }

    categories = [str(r.get(x_key, f"item-{i+1}")) for i, r in enumerate(rows)]
    values = [r.get(y_key, 0) for r in rows]
    return {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [{"name": metric_name, "type": series_type, "smooth": True, "data": values}],
    }


def _echarts_treemap_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    name_key: str | None,
    title: str,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group = str(row.get(x_key, "other"))
        label = str(row.get(name_key, "")) if name_key else group
        size = row.get(y_key, 1)
        size = size if isinstance(size, (int, float)) else 1
        groups.setdefault(group, []).append({"name": label, "value": size})

    tree_data: list[dict[str, Any]]
    if len(groups) <= 1 and not name_key:
        tree_data = [{"name": str(r.get(x_key, f"item-{i+1}")), "value": r.get(y_key, 1)} for i, r in enumerate(rows)]
    else:
        tree_data = [{"name": g, "children": children} for g, children in groups.items()]

    return {
        "tooltip": {"trigger": "item"},
        "series": [{
            "type": "treemap",
            "data": tree_data,
            "label": {"show": True, "formatter": "{b}"},
            "upperLabel": {"show": True, "height": 30},
            "breadcrumb": {"show": True},
            "levels": [
                {"itemStyle": {"borderColor": "#555", "borderWidth": 4, "gapWidth": 4}},
                {"colorSaturation": [0.3, 0.6], "itemStyle": {"borderColorSaturation": 0.7, "gapWidth": 2, "borderWidth": 2}},
            ],
        }],
    }


def _echarts_heatmap_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    series_key: str | None,
) -> dict[str, Any]:
    value_key = series_key or "value"
    x_cats = sorted(set(str(r.get(x_key, "")) for r in rows))
    y_cats = sorted(set(str(r.get(y_key, "")) for r in rows))
    x_map = {v: i for i, v in enumerate(x_cats)}
    y_map = {v: i for i, v in enumerate(y_cats)}
    data = []
    for r in rows:
        xi = x_map.get(str(r.get(x_key, "")), 0)
        yi = y_map.get(str(r.get(y_key, "")), 0)
        val = r.get(value_key, 0)
        data.append([xi, yi, val])
    return {
        "tooltip": {"position": "top"},
        "grid": {"left": "3%", "right": "4%", "bottom": "8%", "containLabel": True},
        "xAxis": {"type": "category", "data": x_cats},
        "yAxis": {"type": "category", "data": y_cats},
        "visualMap": {"min": 0, "max": max((d[2] for d in data), default=1), "calculable": True, "orient": "horizontal", "left": "center", "bottom": "0%"},
        "series": [{"type": "heatmap", "data": data, "label": {"show": True}}],
    }


def _echarts_radar_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    metric_name: str,
) -> dict[str, Any]:
    indicators = [{"name": str(r.get(x_key, f"dim-{i+1}")), "max": 100} for i, r in enumerate(rows)]
    values = [r.get(y_key, 0) for r in rows]
    max_val = max(values, default=100) if values else 100
    for ind in indicators:
        ind["max"] = max_val * 1.2 if max_val > 0 else 100
    return {
        "tooltip": {},
        "radar": {"indicator": indicators},
        "series": [{"type": "radar", "data": [{"name": metric_name, "value": values}]}],
    }


def _echarts_funnel_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    data = [{"name": str(r.get(x_key, f"stage-{i+1}")), "value": r.get(y_key, 0)} for i, r in enumerate(rows)]
    return {
        "tooltip": {"trigger": "item"},
        "legend": {},
        "series": [{"type": "funnel", "left": "10%", "width": "80%", "data": data, "label": {"show": True, "position": "inside"}}],
    }


def _echarts_gauge_option(
    *,
    rows: list[dict[str, Any]],
    y_key: str,
    title: str,
) -> dict[str, Any]:
    value = rows[0].get(y_key, 0) if rows else 0
    return {
        "tooltip": {},
        "series": [{"type": "gauge", "data": [{"value": value, "name": title}], "detail": {"formatter": "{value}"}}],
    }


def _echarts_sankey_option(*, rows: list[dict[str, Any]]) -> dict[str, Any]:
    nodes_set: set[str] = set()
    links: list[dict[str, Any]] = []
    for r in rows:
        src = str(r.get("source", ""))
        tgt = str(r.get("target", ""))
        val = r.get("value", 1)
        if src and tgt:
            nodes_set.add(src)
            nodes_set.add(tgt)
            links.append({"source": src, "target": tgt, "value": val})
    return {
        "tooltip": {"trigger": "item"},
        "series": [{"type": "sankey", "data": [{"name": n} for n in sorted(nodes_set)], "links": links, "emphasis": {"focus": "adjacency"}}],
    }


def _echarts_sunburst_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    if rows and "children" in rows[0]:
        data = rows
    else:
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            g = str(r.get(x_key, "other"))
            groups.setdefault(g, []).append({"name": str(r.get("name", g)), "value": r.get(y_key, 1)})
        data = [{"name": g, "children": c} for g, c in groups.items()]
    return {
        "tooltip": {},
        "series": [{"type": "sunburst", "data": data, "radius": ["15%", "90%"], "label": {"rotate": "radial"}}],
    }


def _echarts_boxplot_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    categories = [str(r.get(x_key, f"cat-{i+1}")) for i, r in enumerate(rows)]
    data = []
    for r in rows:
        val = r.get(y_key)
        if isinstance(val, list):
            data.append(val)
        else:
            v = val if isinstance(val, (int, float)) else 0
            data.append([v, v, v, v, v])
    return {
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [{"type": "boxplot", "data": data}],
    }


def _echarts_graph_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    nodes_set: set[str] = set()
    links: list[dict[str, Any]] = []
    for r in rows:
        src = str(r.get("source", r.get(x_key, "")))
        tgt = str(r.get("target", r.get(y_key, "")))
        if src and tgt:
            nodes_set.add(src)
            nodes_set.add(tgt)
            links.append({"source": src, "target": tgt})
    return {
        "tooltip": {},
        "series": [{
            "type": "graph",
            "layout": "force",
            "data": [{"name": n, "symbolSize": 30} for n in sorted(nodes_set)],
            "links": links,
            "roam": True,
            "label": {"show": True},
            "force": {"repulsion": 200},
        }],
    }


def _echarts_pie_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    data = [{"name": str(r.get(x_key, f"item-{i+1}")), "value": r.get(y_key, 0)} for i, r in enumerate(rows)]
    return {
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left"},
        "series": [{"type": "pie", "radius": "60%", "data": data, "emphasis": {"itemStyle": {"shadowBlur": 10}}}],
    }


def _echarts_scatter_option(
    *,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    data = [[r.get(x_key, 0), r.get(y_key, 0)] for r in rows]
    return {
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "value", "name": x_key},
        "yAxis": {"type": "value", "name": y_key},
        "series": [{"type": "scatter", "data": data, "symbolSize": 10}],
    }


def _guess_dimension_key(rows: list[dict[str, Any]], *, fallback: str) -> str:
    if not rows:
        return fallback
    for key, value in rows[0].items():
        if not isinstance(value, (int, float)):
            return str(key)
    return fallback


def _guess_metric_key(rows: list[dict[str, Any]], *, fallback: str) -> str:
    if not rows:
        return fallback
    sample = rows[0]
    if "metric_value" in sample:
        return "metric_value"
    for key, value in sample.items():
        if isinstance(value, (int, float)):
            return str(key)
    return fallback


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
