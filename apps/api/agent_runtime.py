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
from .agent_prompting import build_agent_system_prompt
from .audit import get_audit_logger
from .chart_strategy import ChartStrategyRouter
from .config import get_settings
from .llm_openai import AgentLLMError, AgentLLMResponse, AgentLLMToolCall, OpenAIAgentLoopClient
from .tool_calling import ToolCall, ToolCallRequest, ToolCallResponse, get_tool_calling_service

logger = logging.getLogger("smarthrbi.agent")

# ---------------------------------------------------------------------------
# OpenAI function-calling definitions for every tool the agent may use
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
]


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
    runtime_backend: str = "llm-react-loop"

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
            runtime_backend=str(record.get("runtime_backend") or "llm-react-loop"),
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
                    json.dumps(state.to_record(), ensure_ascii=False, separators=(",", ":")),
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
# Agent runtime — ReAct loop
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
        self._llm = OpenAIAgentLoopClient(
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

        tool_trace: list[dict[str, Any]] = []
        events: list[tuple[str, dict[str, Any]]] = []

        # Emit planning event
        events.extend(self._planning_events(request=request, session=session))

        # Build the initial message list for the LLM
        messages = self._build_initial_messages(request=request, session=session)

        # ---------- ReAct loop ----------
        max_steps = self.settings.agent_max_tool_steps
        final_answer: dict[str, Any] | None = None
        last_llm_text = ""

        for step in range(1, max_steps + 1):
            logger.info(
                "agent_react_step conversation_id=%s request_id=%s step=%s/%s",
                request.conversation_id,
                request.request_id,
                step,
                max_steps,
            )

            # Call LLM
            try:
                llm_response = self._llm.chat(
                    messages=messages,
                    conversation_id=request.conversation_id,
                    step=step,
                )
            except AgentLLMError as exc:
                raise AgentRuntimeError(
                    code="AGENT_LLM_FAILED",
                    message=f"LLM call failed at step {step}: {exc.message}",
                    should_fallback=False,
                ) from exc

            last_llm_text = llm_response.content

            # Append assistant message (content + tool_calls) to history
            assistant_msg = _build_assistant_message(llm_response)
            messages.append(assistant_msg)

            # If the LLM returned no tool calls → it's done (or gave up)
            if not llm_response.tool_calls:
                # Try to parse a structured final answer from the content
                final_answer = _parse_final_answer(llm_response.content)
                if final_answer is not None:
                    logger.info(
                        "agent_react_final_answer conversation_id=%s request_id=%s step=%s",
                        request.conversation_id,
                        request.request_id,
                        step,
                    )
                else:
                    logger.warning(
                        "agent_react_no_tool_no_answer conversation_id=%s request_id=%s step=%s content=%r",
                        request.conversation_id,
                        request.request_id,
                        step,
                        llm_response.content[:200],
                    )
                break

            # Execute all tool calls the LLM requested
            tool_results_msgs: list[dict[str, Any]] = []
            for tc in llm_response.tool_calls:
                tool_result = self._execute_tool_call(
                    tool_call=tc,
                    request=request,
                    session=session,
                    tool_trace=tool_trace,
                    events=events,
                    step=step,
                )
                # Build the tool result message for the next LLM turn
                tool_results_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.call_id,
                        "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                    }
                )

            # Append all tool results before the next LLM call
            messages.extend(tool_results_msgs)

        # ------ Build chart spec from final answer ------
        if final_answer is not None:
            spec = self._spec_from_final_answer(final_answer, request=request)
            final_text = _compose_final_text(final_answer)
            result_payload = final_answer
        else:
            # LLM didn't return a structured answer — produce an empty spec
            spec = self._empty_spec(request=request)
            final_text = last_llm_text or "Agent did not return a usable answer."
            result_payload = {"rows": [], "conclusion": final_text}

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
            runtime_backend="llm-react-loop",
        )
        with self._lock:
            self._hot_sessions[conversation_id] = session
        self._store.save(session)
        return session

    def _build_initial_messages(
        self,
        *,
        request: AgentRequest,
        session: AgentSessionState,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        # Include recent conversation history for multi-turn context
        for item in session.history[-10:]:
            role = str(item.get("role") or "")
            content = item.get("content") or ""
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": str(content)})

        # Context hint about active dataset and all available tables
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
                "You may JOIN across these tables in execute_readonly_sql when answering cross-table questions. "
                "Always call describe_table on each table you plan to JOIN before writing SQL. "
            )
        else:
            tables_hint = f"Active dataset table: `{request.dataset_table}`. "

        context_hint = (
            tables_hint
            + f"User role: {request.role}. "
            + "Row-level security is enforced automatically on all queries."
        )
        messages.append({"role": "system", "content": context_hint})
        messages.append({"role": "user", "content": request.message})
        return messages

    def _planning_events(
        self,
        *,
        request: AgentRequest,
        session: AgentSessionState,
    ) -> list[tuple[str, dict[str, Any]]]:
        text = (
            "Starting ReAct reasoning loop. Will inspect schema, understand data, "
            "then iteratively call tools until a complete answer can be formed."
        )
        payload = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "text": text,
            "system_prompt": self.system_prompt,
        }
        compatibility = {
            "conversation_id": request.conversation_id,
            "request_id": request.request_id,
            "agent_session_id": session.agent_session_id,
            "text": text,
            "compatibility_mirror": True,
        }
        return [("planning", payload), ("reasoning", compatibility)]

    def _execute_tool_call(
        self,
        *,
        tool_call: AgentLLMToolCall,
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

    def _spec_from_final_answer(
        self,
        answer: dict[str, Any],
        *,
        request: AgentRequest,
    ) -> dict[str, Any]:
        rows = list(answer.get("rows") or [])
        chart_type = str(answer.get("chart_type") or "bar")
        if chart_type not in {"bar", "line", "pie", "table", "single_value"}:
            chart_type = "bar"
        if not rows:
            chart_type = "empty"

        x_key = str(answer.get("x_key") or _guess_dimension_key(rows, fallback="dimension"))
        y_key = str(answer.get("y_key") or _guess_metric_key(rows, fallback="metric_value"))
        series_key = answer.get("series_key") or None
        metric_name = str(answer.get("metric_name") or "metric")
        title = str(answer.get("title") or request.message[:60])

        engine = "recharts"
        if chart_type == "line" and series_key:
            engine = "echarts"

        config: dict[str, Any] = {"xKey": x_key, "yKey": y_key, "metricName": metric_name}
        if series_key:
            config["seriesKey"] = series_key

        return {
            "engine": engine,
            "chart_type": chart_type,
            "title": title,
            "data": rows,
            "config": config,
            "route": {
                "complexity_score": len(rows) + (3 if series_key else 1),
                "threshold": self.router.COMPLEXITY_THRESHOLD,
                "reasons": ["llm_react_loop"],
                "selected_engine": engine,
            },
            "meta": {"intent": request.message, "generated_by": "agent_runtime_react"},
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
            "meta": {"intent": request.message, "generated_by": "agent_runtime_react"},
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


def _build_assistant_message(llm_response: AgentLLMResponse) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant"}
    if llm_response.content:
        msg["content"] = llm_response.content
    if llm_response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.call_id,
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in llm_response.tool_calls
        ]
    return msg


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
