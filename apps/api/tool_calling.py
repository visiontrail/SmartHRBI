from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
from typing import Any, Callable, Literal

import duckdb
from pydantic import BaseModel, Field

from .config import get_settings
from .data_policy import (
    filter_schema_columns,
    forbidden_sensitive_columns,
    redact_rows,
    redact_structure,
)
from .datasets import get_dataset_service
from .security import (
    AccessContext,
    QueryAccessError,
    RLSInjector,
    RLSError,
    SQLGuardError,
    SQLReadOnlyValidator,
    secure_query_sql,
)
from .semantic import (
    IntentParser,
    MetricCompileError,
    QueryFilter,
    SemanticQueryAST,
    get_metric_compiler,
    get_semantic_registry,
)
from .views import SaveViewInput, ViewStorageError, get_view_storage_service

SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ToolCall(BaseModel):
    name: Literal["query_metrics", "describe_dataset", "save_view"]
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    conversation_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    idempotency_key: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str
    project_id: str
    dataset_table: str
    role: str = "viewer"
    department: str | None = None
    clearance: int = 0
    retry_limit: int = Field(default=2, ge=0, le=2)
    tool: ToolCall


class ToolCallResponse(BaseModel):
    conversation_id: str
    request_id: str
    idempotency_key: str
    tool_name: str
    status: Literal["success", "error"]
    attempts: int
    from_cache: bool = False
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class ToolExecutionError(Exception):
    def __init__(self, *, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(slots=True)
class ToolContext:
    user_id: str
    project_id: str
    dataset_table: str
    role: str
    department: str | None
    clearance: int


class ToolCallingService:
    def __init__(self) -> None:
        settings = get_settings()
        self.dataset_service = get_dataset_service(settings.upload_dir)
        self.registry = get_semantic_registry()
        self.compiler = get_metric_compiler()
        self.intent_parser = IntentParser(self.registry)
        self.view_storage = get_view_storage_service()

        self._idempotency_cache: dict[str, ToolCallResponse] = {}
        self._transient_failures: dict[str, int] = {}
        self._lock = Lock()

        self._tools: dict[str, Callable[[ToolContext, dict[str, Any]], dict[str, Any]]] = {
            "query_metrics": self._tool_query_metrics,
            "describe_dataset": self._tool_describe_dataset,
            "save_view": self._tool_save_view,
        }

    def invoke(self, request: ToolCallRequest) -> ToolCallResponse:
        with self._lock:
            cached = self._idempotency_cache.get(request.idempotency_key)
        if cached is not None:
            return cached.model_copy(update={"from_cache": True})

        tool = self._tools.get(request.tool.name)
        if tool is None:
            response = ToolCallResponse(
                conversation_id=request.conversation_id,
                request_id=request.request_id,
                idempotency_key=request.idempotency_key,
                tool_name=request.tool.name,
                status="error",
                attempts=0,
                error={
                    "code": "TOOL_NOT_FOUND",
                    "message": f"Unsupported tool: {request.tool.name}",
                    "retryable": False,
                },
            )
            with self._lock:
                self._idempotency_cache[request.idempotency_key] = response
            return response

        context = ToolContext(
            user_id=request.user_id,
            project_id=request.project_id,
            dataset_table=request.dataset_table,
            role=request.role,
            department=request.department,
            clearance=request.clearance,
        )

        max_attempts = request.retry_limit + 1
        attempts = 0
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                result = tool(context, request.tool.arguments)
                response = ToolCallResponse(
                    conversation_id=request.conversation_id,
                    request_id=request.request_id,
                    idempotency_key=request.idempotency_key,
                    tool_name=request.tool.name,
                    status="success",
                    attempts=attempt,
                    result=result,
                )
                with self._lock:
                    self._idempotency_cache[request.idempotency_key] = response
                return response
            except ToolExecutionError as exc:
                if exc.retryable and attempt < max_attempts:
                    continue

                if exc.retryable:
                    detail = {
                        "code": "TOOL_RETRY_EXHAUSTED",
                        "message": "Tool failed after retry attempts",
                        "retryable": False,
                        "last_error": exc.to_detail(),
                    }
                else:
                    detail = exc.to_detail()

                response = ToolCallResponse(
                    conversation_id=request.conversation_id,
                    request_id=request.request_id,
                    idempotency_key=request.idempotency_key,
                    tool_name=request.tool.name,
                    status="error",
                    attempts=attempt,
                    error=detail,
                )
                with self._lock:
                    self._idempotency_cache[request.idempotency_key] = response
                return response
            except Exception:
                response = ToolCallResponse(
                    conversation_id=request.conversation_id,
                    request_id=request.request_id,
                    idempotency_key=request.idempotency_key,
                    tool_name=request.tool.name,
                    status="error",
                    attempts=attempt,
                    error={
                        "code": "TOOL_INTERNAL_ERROR",
                        "message": "Unexpected tool failure",
                        "retryable": False,
                    },
                )
                with self._lock:
                    self._idempotency_cache[request.idempotency_key] = response
                return response

        # Defensive fallback (should never happen because the loop always returns).
        response = ToolCallResponse(
            conversation_id=request.conversation_id,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            tool_name=request.tool.name,
            status="error",
            attempts=attempts,
            error={
                "code": "TOOL_INTERNAL_ERROR",
                "message": "Unexpected execution path",
                "retryable": False,
            },
        )
        with self._lock:
            self._idempotency_cache[request.idempotency_key] = response
        return response

    def clear_runtime_state(self) -> None:
        with self._lock:
            self._idempotency_cache.clear()
            self._transient_failures.clear()

    def _tool_query_metrics(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            query_ast = self._build_query_ast(arguments)
            compiled = self.compiler.compile(query_ast, table_override=context.dataset_table)
        except MetricCompileError as exc:
            raise ToolExecutionError(
                code=exc.code,
                message=exc.message,
                retryable=False,
            ) from exc

        guard = SQLReadOnlyValidator(
            allowed_tables={context.dataset_table},
            sensitive_tables={"raw_payroll", "security_audit_log"},
            sensitive_columns=forbidden_sensitive_columns(context.role),
        )
        rls_injector = RLSInjector()
        access_context = AccessContext(
            user_id=context.user_id,
            role=context.role,
            department=context.department,
            clearance=context.clearance,
        )

        try:
            secure_sql = secure_query_sql(
                compiled.sql,
                context=access_context,
                guard=guard,
                rls_injector=rls_injector,
            )
        except QueryAccessError as exc:
            raise ToolExecutionError(
                code=exc.code,
                message=exc.message,
                retryable=False,
            ) from exc
        except (SQLGuardError, RLSError) as exc:
            raise ToolExecutionError(
                code=exc.code,
                message=exc.message,
                retryable=False,
            ) from exc

        try:
            with self.dataset_service.session_manager.connection(context.user_id, context.project_id) as conn:
                cursor = conn.execute(secure_sql)
                columns = [column[0] for column in (cursor.description or [])]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        except duckdb.Error as exc:
            raise ToolExecutionError(
                code="QUERY_EXECUTION_FAILED",
                message="Failed to execute semantic query",
                retryable=True,
            ) from exc

        safe_rows = redact_rows(rows, role=context.role)

        return {
            "metric": compiled.metric,
            "query_ast": {
                "metric": query_ast.metric,
                "group_by": query_ast.group_by,
                "filters": [
                    {"field": item.field, "op": item.op, "value": item.value}
                    for item in query_ast.filters
                ],
                "limit": query_ast.limit,
            },
            "sql": secure_sql,
            "explain": compiled.explain,
            "row_count": len(safe_rows),
            "rows": safe_rows,
        }

    def _tool_describe_dataset(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        sample_limit = int(arguments.get("sample_limit", 5))
        sample_limit = max(1, min(sample_limit, 50))
        table = _safe_identifier(context.dataset_table)

        try:
            with self.dataset_service.session_manager.connection(context.user_id, context.project_id) as conn:
                column_rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                row_count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                cursor = conn.execute(f'SELECT * FROM "{table}" LIMIT {sample_limit}')
                columns = [column[0] for column in (cursor.description or [])]
                sample_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        except duckdb.Error as exc:
            raise ToolExecutionError(
                code="DATASET_DESCRIBE_FAILED",
                message="Failed to inspect dataset table",
                retryable=True,
            ) from exc

        typed_columns = [
            {
                "name": str(item[1]),
                "type": str(item[2]),
                "nullable": not bool(item[3]),
                "primary_key": bool(item[5]),
            }
            for item in column_rows
        ]
        safe_columns = filter_schema_columns(typed_columns, role=context.role)
        safe_rows = redact_rows(sample_rows, role=context.role)

        return {
            "table": table,
            "row_count": row_count,
            "sample_limit": sample_limit,
            "columns": safe_columns,
            "sample_rows": safe_rows,
        }

    def _tool_save_view(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        failure_key = str(arguments.get("failure_key", "")).strip()
        failure_times = int(arguments.get("simulate_retryable_failures", 0))
        if failure_key and failure_times > 0:
            current = self._transient_failures.get(failure_key, 0)
            if current < failure_times:
                self._transient_failures[failure_key] = current + 1
                raise ToolExecutionError(
                    code="SAVE_VIEW_TEMPORARY_FAILURE",
                    message="Temporary view storage error",
                    retryable=True,
                )

        chart_spec = arguments.get("chart_spec")
        sql = arguments.get("sql")
        if chart_spec is None and sql is None:
            raise ToolExecutionError(
                code="INVALID_VIEW_PAYLOAD",
                message="save_view requires at least one of chart_spec or sql",
                retryable=False,
            )

        title = str(arguments.get("title") or "Saved View").strip() or "Saved View"
        metadata = arguments.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ToolExecutionError(
                code="INVALID_VIEW_PAYLOAD",
                message="metadata must be an object",
                retryable=False,
            )

        ai_state = {
            "conversation_id": arguments.get("conversation_id"),
            "chart_spec": chart_spec,
            "sql": sql,
            "metadata": metadata,
        }
        safe_ai_state = redact_structure(ai_state, role=context.role)

        try:
            result = self.view_storage.save_view(
                SaveViewInput(
                    user_id=context.user_id,
                    project_id=context.project_id,
                    dataset_table=context.dataset_table,
                    role=context.role,
                    department=context.department,
                    clearance=context.clearance,
                    title=title,
                    ai_state=safe_ai_state,
                    conversation_id=arguments.get("conversation_id"),
                    view_id=arguments.get("view_id"),
                    metadata=metadata,
                )
            )
        except ViewStorageError as exc:
            raise ToolExecutionError(
                code=exc.code,
                message=exc.message,
                retryable=False,
            ) from exc

        return {
            "view_id": result["view_id"],
            "title": result["title"],
            "version": result["version"],
            "share_path": result["share_path"],
            "saved_at": result["saved_at"],
        }

    def _build_query_ast(self, arguments: dict[str, Any]) -> SemanticQueryAST:
        explicit_filters = _parse_filters(arguments.get("filters", []))
        raw_group_by = arguments.get("group_by", [])
        if raw_group_by is None:
            raw_group_by = []
        if not isinstance(raw_group_by, list):
            raise ToolExecutionError(
                code="INVALID_GROUP_BY",
                message="group_by must be a list",
                retryable=False,
            )
        group_by = [str(item) for item in raw_group_by]

        limit = arguments.get("limit")
        if limit is not None:
            limit = int(limit)

        metric = arguments.get("metric")
        if metric:
            return SemanticQueryAST(
                metric=str(metric),
                group_by=group_by,
                filters=explicit_filters,
                limit=limit,
            )

        intent = arguments.get("intent")
        if intent:
            parsed = self.intent_parser.parse(str(intent))
            merged_group_by = group_by or parsed.group_by
            merged_filters = [*parsed.filters, *explicit_filters]
            return SemanticQueryAST(
                metric=parsed.metric,
                group_by=merged_group_by,
                filters=merged_filters,
                limit=limit,
            )

        raise ToolExecutionError(
            code="MISSING_QUERY_TARGET",
            message="query_metrics requires metric or intent",
            retryable=False,
        )


def _parse_filters(raw_filters: Any) -> list[QueryFilter]:
    if raw_filters is None:
        return []
    if not isinstance(raw_filters, list):
        raise ToolExecutionError(
            code="INVALID_FILTERS",
            message="filters must be a list",
            retryable=False,
        )

    parsed: list[QueryFilter] = []
    for item in raw_filters:
        if not isinstance(item, dict):
            raise ToolExecutionError(
                code="INVALID_FILTERS",
                message="Each filter must be an object",
                retryable=False,
            )
        field = str(item.get("field", "")).strip()
        if not field:
            raise ToolExecutionError(
                code="INVALID_FILTERS",
                message="Filter field is required",
                retryable=False,
            )
        op = str(item.get("op", "eq"))
        parsed.append(
            QueryFilter(
                field=field,
                op=op,
                value=item.get("value"),
            )
        )

    return parsed


@lru_cache(maxsize=2)
def _cached_tool_calling_service(settings_key: str) -> ToolCallingService:
    _ = settings_key
    return ToolCallingService()


def get_tool_calling_service() -> ToolCallingService:
    settings = get_settings()
    return _cached_tool_calling_service(str(settings.upload_dir.resolve()))


def clear_tool_calling_service_cache() -> None:
    _cached_tool_calling_service.cache_clear()


def _safe_identifier(value: str) -> str:
    if not SAFE_IDENTIFIER_RE.match(value):
        raise ToolExecutionError(
            code="INVALID_IDENTIFIER",
            message=f"Invalid identifier: {value}",
            retryable=False,
        )
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
