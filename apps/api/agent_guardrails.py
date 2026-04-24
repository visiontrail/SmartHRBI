from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import get_settings
from .data_policy import forbidden_sensitive_columns

FORBIDDEN_MESSAGE_PATTERNS = (
    (re.compile(r"ignore (all|previous) instructions", re.IGNORECASE), "PROMPT_INJECTION_BLOCKED"),
    (re.compile(r"system prompt|developer message", re.IGNORECASE), "PROMPT_INJECTION_BLOCKED"),
    (re.compile(r"\b(bash|terminal|shell|filesystem|read file|write file|edit file)\b", re.IGNORECASE), "TOOL_SURFACE_VIOLATION"),
    (re.compile(r"\b(websearch|webfetch|curl|wget|browser)\b", re.IGNORECASE), "TOOL_SURFACE_VIOLATION"),
)

FORBIDDEN_SQL_PATTERNS = (
    (re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|merge|copy)\b", re.IGNORECASE), "READ_ONLY_ONLY_SELECT"),
    (re.compile(r"\bcross\s+join\b", re.IGNORECASE), "SQL_BUDGET_EXCEEDED"),
    (re.compile(r"\bgenerate_series\b", re.IGNORECASE), "SQL_BUDGET_EXCEEDED"),
)


class AgentGuardrailError(Exception):
    def __init__(self, *, code: str, message: str, should_fallback: bool = False) -> None:
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
class AgentGuardrailContext:
    role: str
    user_id: str
    project_id: str


class AgentGuardrails:
    def __init__(self) -> None:
        settings = get_settings()
        self.max_sql_rows = settings.agent_max_sql_rows
        self.max_sql_scan_rows = settings.agent_max_sql_scan_rows
        self._allowed_tools = (
            "list_tables",
            "describe_table",
            "sample_rows",
            "get_metric_catalog",
            "run_semantic_query",
            "execute_readonly_sql",
            "get_distinct_values",
            "save_view",
        )

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return self._allowed_tools

    def validate_user_message(self, *, message: str, context: AgentGuardrailContext) -> None:
        for pattern, code in FORBIDDEN_MESSAGE_PATTERNS:
            if pattern.search(message):
                raise AgentGuardrailError(
                    code=code,
                    message="The agent can only use the Cognitrix BI tool surface.",
                )

        lowered = message.lower()
        for column in forbidden_sensitive_columns(context.role):
            token = column.replace("_", " ")
            if column in lowered or token in lowered:
                raise AgentGuardrailError(
                    code="SENSITIVE_FIELD_FORBIDDEN",
                    message=f"Access to sensitive field '{column}' is not allowed for this role.",
                )

    def validate_tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: AgentGuardrailContext,
    ) -> None:
        _ = context
        if tool_name not in self._allowed_tools:
            raise AgentGuardrailError(
                code="TOOL_NOT_ALLOWED",
                message=f"Tool '{tool_name}' is outside the allowed BI surface.",
            )

        if tool_name != "execute_readonly_sql":
            return

        sql = str(arguments.get("sql", "")).strip()
        if not sql:
            raise AgentGuardrailError(
                code="SQL_REQUIRED",
                message="execute_readonly_sql requires a SQL string.",
            )

        for pattern, code in FORBIDDEN_SQL_PATTERNS:
            if pattern.search(sql):
                raise AgentGuardrailError(
                    code=code,
                    message="The SQL request exceeds the allowed readonly budget.",
                )

        requested_max_rows = int(arguments.get("max_rows", self.max_sql_rows))
        if requested_max_rows > self.max_sql_rows:
            raise AgentGuardrailError(
                code="SQL_RESULT_LIMIT_EXCEEDED",
                message=f"Requested row limit exceeds {self.max_sql_rows}.",
            )

        limit_match = re.search(r"\blimit\s+(\d+)\b", sql, re.IGNORECASE)
        if limit_match and int(limit_match.group(1)) > self.max_sql_scan_rows:
            raise AgentGuardrailError(
                code="SQL_BUDGET_EXCEEDED",
                message="The SQL limit exceeds the configured scan budget.",
            )
