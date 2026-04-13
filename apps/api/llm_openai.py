from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .agent_logging import format_agent_debug_blocks

logger = logging.getLogger("smarthrbi.llm")


# ---------------------------------------------------------------------------
# Agent loop LLM client
# ---------------------------------------------------------------------------


class AgentLLMError(Exception):
    """Raised when the LLM call in the agent ReAct loop fails."""

    def __init__(self, *, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class AgentLLMToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class AgentLLMResponse:
    """One turn of the LLM in the ReAct loop."""

    content: str  # text thinking / final answer (may be empty when tool_calls present)
    tool_calls: list[AgentLLMToolCall]
    finish_reason: str  # "stop", "tool_calls", "length", ...


class OpenAIAgentLoopClient:
    """OpenAI-compatible chat-completions client used by the ReAct agent loop.

    Sends a full conversation history including tool results and returns either
    tool_calls (the model wants to call tools) or a final text response.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        tool_definitions: list[dict[str, Any]],
    ) -> None:
        self.base_url = base_url.strip()
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.tool_definitions = tool_definitions

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        conversation_id: str,
        step: int,
    ) -> AgentLLMResponse:
        if not self.enabled:
            raise AgentLLMError(message="LLM agent loop client is not configured")

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
        }
        if self.tool_definitions:
            payload["tools"] = self.tool_definitions
            payload["tool_choice"] = "auto"

        endpoint = _chat_completions_endpoint(self.base_url)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")
        started_at = time.perf_counter()

        logger.info(
            "agent_llm_request conversation_id=%s step=%s endpoint=%s model=%s message_count=%s",
            conversation_id,
            step,
            endpoint,
            self.model,
            len(messages),
        )
        logger.info(
            "agent_llm_request_debug conversation_id=%s step=%s\n%s",
            conversation_id,
            step,
            format_agent_debug_blocks(
                ai_input={
                    "conversation_id": conversation_id,
                    "step": step,
                    "endpoint": endpoint,
                    "model": self.model,
                    "messages": messages,
                    "tools": self.tool_definitions,
                },
            ),
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except TimeoutError as exc:
            self._log_failure(endpoint=endpoint, step=step, error=exc, started_at=started_at)
            raise AgentLLMError(message="LLM request timed out") from exc
        except socket.timeout as exc:
            self._log_failure(endpoint=endpoint, step=step, error=exc, started_at=started_at)
            raise AgentLLMError(message="LLM request timed out") from exc
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            self._log_failure(endpoint=endpoint, step=step, error=exc, started_at=started_at, details=details)
            raise AgentLLMError(
                message=f"LLM HTTP error ({exc.code}): {details or exc.reason}",
            ) from exc
        except urllib_error.URLError as exc:
            self._log_failure(endpoint=endpoint, step=step, error=exc, started_at=started_at)
            raise AgentLLMError(message=f"LLM request failed: {exc.reason}") from exc

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "agent_llm_response conversation_id=%s step=%s elapsed_ms=%s",
            conversation_id,
            step,
            elapsed_ms,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "agent_llm_response_debug conversation_id=%s step=%s\n%s",
                conversation_id,
                step,
                format_agent_debug_blocks(
                    ai_output={
                        "conversation_id": conversation_id,
                        "step": step,
                        "elapsed_ms": elapsed_ms,
                        "raw_response": raw,
                    },
                    thinking=raw,
                ),
            )
            raise AgentLLMError(message="LLM returned non-JSON response") from exc

        parsed = self._parse_response(data)
        logger.info(
            "agent_llm_response_debug conversation_id=%s step=%s\n%s",
            conversation_id,
            step,
            format_agent_debug_blocks(
                ai_output={
                    "conversation_id": conversation_id,
                    "step": step,
                    "elapsed_ms": elapsed_ms,
                    "raw_response": data,
                    "parsed_response": {
                        "finish_reason": parsed.finish_reason,
                        "content": parsed.content,
                        "tool_calls": [
                            {
                                "call_id": item.call_id,
                                "tool_name": item.tool_name,
                                "arguments": item.arguments,
                            }
                            for item in parsed.tool_calls
                        ],
                    },
                },
                thinking=parsed.content,
            ),
        )
        return parsed

    def _parse_response(self, data: dict[str, Any]) -> AgentLLMResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AgentLLMError(message="LLM response missing choices")

        first = choices[0]
        if not isinstance(first, dict):
            raise AgentLLMError(message="LLM choice is not an object")

        finish_reason = str(first.get("finish_reason") or "stop")
        message = first.get("message") or {}
        content = str(message.get("content") or "").strip()

        raw_tool_calls = message.get("tool_calls") or []
        tool_calls: list[AgentLLMToolCall] = []
        for tc in raw_tool_calls:
            if not isinstance(tc, dict):
                continue
            call_id = str(tc.get("id") or "")
            fn = tc.get("function") or {}
            tool_name = str(fn.get("name") or "").strip()
            raw_args = fn.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            if tool_name:
                tool_calls.append(AgentLLMToolCall(call_id=call_id, tool_name=tool_name, arguments=arguments))

        return AgentLLMResponse(content=content, tool_calls=tool_calls, finish_reason=finish_reason)

    def _log_failure(
        self,
        *,
        endpoint: str,
        step: int,
        error: Exception,
        started_at: float,
        details: str | None = None,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.warning(
            "agent_llm_error endpoint=%s step=%s elapsed_ms=%s error_type=%s error=%s details=%s",
            endpoint,
            step,
            elapsed_ms,
            type(error).__name__,
            str(error),
            details or "",
        )
        logger.warning(
            "agent_llm_error_debug step=%s\n%s",
            step,
            format_agent_debug_blocks(
                ai_output={
                    "endpoint": endpoint,
                    "step": step,
                    "elapsed_ms": elapsed_ms,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "details": details or "",
                },
                thinking=str(error),
            ),
        )


class ToolSelectionError(Exception):
    def __init__(self, *, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class ToolSelectionResult:
    tool_name: str
    arguments: dict[str, Any]


class OpenAICompatibleToolSelector:
    _VALID_TOOLS = {"query_metrics", "describe_dataset", "save_view"}
    _ALLOWED_GROUP_BY = {"department", "project", "region", "manager", "status"}

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        metric_catalog: list[dict[str, Any]],
    ) -> None:
        self.base_url = base_url.strip()
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.metric_catalog = metric_catalog
        self.metric_names = {str(item.get("name", "")).strip() for item in metric_catalog}

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def select_tool(
        self,
        *,
        message: str,
        conversation_id: str,
        context: dict[str, Any],
    ) -> ToolSelectionResult:
        if not self.enabled:
            raise ToolSelectionError(message="LLM selector is not enabled")

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": self._build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "conversation_id": conversation_id,
                            "message": message,
                            "available_metrics": self.metric_catalog,
                            "has_latest_spec": bool(context.get("latest_spec")),
                            "has_latest_sql": bool(context.get("latest_sql")),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        raw = self._post_chat_completions(payload)
        parsed = self._extract_tool_payload(raw)

        tool_name = str(parsed.get("tool", "")).strip()
        arguments = parsed.get("arguments", {})
        if tool_name not in self._VALID_TOOLS:
            raise ToolSelectionError(message=f"Invalid tool from LLM: {tool_name}")
        if not isinstance(arguments, dict):
            arguments = {}

        if (
            tool_name == "query_metrics"
            and not str(arguments.get("metric") or "").strip()
            and _looks_like_custom_dataset_analysis(message)
        ):
            logger.info(
                "llm_tool_selector_reroute conversation_id=%s from_tool=%s to_tool=describe_dataset reason=custom_dataset_analysis",
                conversation_id,
                tool_name,
            )
            tool_name = "describe_dataset"
            arguments = {"sample_limit": 10}

        return ToolSelectionResult(
            tool_name=tool_name,
            arguments=self._sanitize_arguments(
                tool_name=tool_name,
                arguments=arguments,
                message=message,
                context=context,
                conversation_id=conversation_id,
            ),
        )

    def _build_system_prompt(self) -> str:
        return (
            "You are a SmartHRBI router. Return only one JSON object with keys: tool, arguments. "
            "tool must be one of query_metrics, describe_dataset, save_view. "
            "Use describe_dataset for schema/field/column/sample requests. "
            "Also use describe_dataset for custom raw-column analysis that is not directly covered by an available metric, "
            "including distribution/histogram/bucketing/year-extraction requests such as salary distribution or hire year distribution. "
            "Use save_view when user asks to save/bookmark current result. "
            "Otherwise use query_metrics. "
            "For query_metrics arguments, prefer metric only when exactly matching an available metric name; "
            "otherwise set intent to the original user message. Never guess a metric for unsupported long-tail analysis. "
            "Allowed group_by values: department, project, region, manager, status. "
            "Do not output markdown."
        )

    def _sanitize_arguments(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        message: str,
        context: dict[str, Any],
        conversation_id: str,
    ) -> dict[str, Any]:
        if tool_name == "describe_dataset":
            sample_limit = arguments.get("sample_limit", 10)
            try:
                parsed_limit = int(sample_limit)
            except (TypeError, ValueError):
                parsed_limit = 10
            return {"sample_limit": max(1, min(parsed_limit, 50))}

        if tool_name == "save_view":
            title = str(arguments.get("title") or "Saved from Chat").strip() or "Saved from Chat"
            return {
                "title": title,
                "chart_spec": context.get("latest_spec"),
                "sql": context.get("latest_sql"),
                "conversation_id": conversation_id,
            }

        metric = str(arguments.get("metric") or "").strip()
        group_by: list[str] = []
        raw_group_by = arguments.get("group_by", [])
        if isinstance(raw_group_by, list):
            for item in raw_group_by:
                token = str(item).strip()
                if token and token in self._ALLOWED_GROUP_BY and token not in group_by:
                    group_by.append(token)

        filters: list[dict[str, Any]] = []
        raw_filters = arguments.get("filters")
        if isinstance(raw_filters, list):
            for item in raw_filters:
                if not isinstance(item, dict):
                    continue
                field = str(item.get("field") or "").strip()
                if not field:
                    continue
                op = str(item.get("op") or "eq").strip() or "eq"
                filters.append({"field": field, "op": op, "value": item.get("value")})

        intent = str(arguments.get("intent") or message)
        payload: dict[str, Any] = {
            "intent": intent,
            "group_by": group_by,
        }
        if metric and metric in self.metric_names:
            payload["metric"] = metric
        if filters:
            payload["filters"] = filters

        if "limit" in arguments:
            try:
                parsed_limit = int(arguments["limit"])
                if parsed_limit > 0:
                    payload["limit"] = min(parsed_limit, 500)
            except (TypeError, ValueError):
                pass

        return payload

    def _post_chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = _chat_completions_endpoint(self.base_url)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        started_at = time.perf_counter()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")
        logger.info(
            "llm_tool_selector_request endpoint=%s model=%s timeout_seconds=%s payload=%s",
            endpoint,
            self.model,
            self.timeout_seconds,
            _compact_json(payload),
        )
        logger.info(
            "llm_tool_selector_request_debug\n%s",
            format_agent_debug_blocks(
                ai_input={
                    "endpoint": endpoint,
                    "model": self.model,
                    "timeout_seconds": self.timeout_seconds,
                    "payload": payload,
                },
            ),
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "llm_tool_selector_response endpoint=%s model=%s elapsed_ms=%s body=%s",
                endpoint,
                self.model,
                elapsed_ms,
                raw,
            )
            logger.info(
                "llm_tool_selector_response_debug\n%s",
                format_agent_debug_blocks(
                    ai_output={
                        "endpoint": endpoint,
                        "model": self.model,
                        "elapsed_ms": elapsed_ms,
                        "body": raw,
                    },
                    thinking=raw,
                ),
            )
        except TimeoutError as exc:
            self._log_request_failure(
                endpoint=endpoint,
                payload=payload,
                error=exc,
                started_at=started_at,
            )
            raise ToolSelectionError(message="LLM provider request timed out") from exc
        except socket.timeout as exc:
            self._log_request_failure(
                endpoint=endpoint,
                payload=payload,
                error=exc,
                started_at=started_at,
            )
            raise ToolSelectionError(message="LLM provider request timed out") from exc
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            self._log_request_failure(
                endpoint=endpoint,
                payload=payload,
                error=exc,
                started_at=started_at,
                details=details or exc.reason,
            )
            raise ToolSelectionError(
                message=f"LLM provider HTTP error ({exc.code}): {details or exc.reason}",
            ) from exc
        except urllib_error.URLError as exc:
            self._log_request_failure(
                endpoint=endpoint,
                payload=payload,
                error=exc,
                started_at=started_at,
            )
            raise ToolSelectionError(message=f"LLM provider request failed: {exc.reason}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolSelectionError(message="LLM provider returned non-JSON response") from exc

    def _log_request_failure(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        error: Exception,
        started_at: float,
        details: str | None = None,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.warning(
            "llm_tool_selector_error endpoint=%s model=%s timeout_seconds=%s elapsed_ms=%s error_type=%s error=%s details=%s payload=%s",
            endpoint,
            self.model,
            self.timeout_seconds,
            elapsed_ms,
            type(error).__name__,
            str(error),
            details or "",
            _compact_json(payload),
        )
        logger.warning(
            "llm_tool_selector_error_debug\n%s",
            format_agent_debug_blocks(
                ai_input={
                    "endpoint": endpoint,
                    "model": self.model,
                    "timeout_seconds": self.timeout_seconds,
                    "payload": payload,
                },
                ai_output={
                    "elapsed_ms": elapsed_ms,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "details": details or "",
                },
                thinking=str(error),
            ),
        )

    def _extract_tool_payload(self, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ToolSelectionError(message="LLM response missing choices")

        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None

        text = _content_to_text(content)
        if not text:
            raise ToolSelectionError(message="LLM response content is empty")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = _json_from_text_block(text)

        if not isinstance(parsed, dict):
            raise ToolSelectionError(message="LLM response JSON is not an object")
        return parsed


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks).strip()

    return ""


def _json_from_text_block(value: str) -> dict[str, Any]:
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ToolSelectionError(message="LLM output does not contain JSON object")

    snippet = value[start : end + 1]
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise ToolSelectionError(message="Unable to parse JSON object from LLM output") from exc

    if not isinstance(parsed, dict):
        raise ToolSelectionError(message="Parsed JSON payload must be an object")
    return parsed


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _looks_like_custom_dataset_analysis(message: str) -> bool:
    normalized = message.lower()
    return any(
        token in normalized
        for token in (
            "分布",
            "histogram",
            "distribution",
            "bucket",
            "区间",
            "年份统计",
            "year distribution",
            "hire year",
        )
    )
