from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .agent_logging import format_agent_debug_blocks

logger = logging.getLogger("smarthrbi.llm_anthropic")


class AnthropicLLMError(Exception):
    """Raised when the LLM call in the agent loop fails."""

    def __init__(self, *, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(slots=True)
class AnthropicToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class AnthropicLLMResponse:
    content: str
    thinking: str
    tool_calls: list[AnthropicToolCall]
    stop_reason: str
    raw_content_blocks: list[Any] = field(default_factory=list)


def build_anthropic_content_blocks(response: AnthropicLLMResponse) -> dict[str, Any]:
    """Build an OpenAI-format assistant message dict from an LLM response.

    Despite the legacy name, this now produces OpenAI chat-completions format
    so it can be appended directly into the message history sent to
    OpenAI-compatible providers (Kimi, DeepSeek, etc.).
    """
    msg: dict[str, Any] = {"role": "assistant", "content": response.content or None}
    if response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.call_id,
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in response.tool_calls
        ]
    return msg


class AnthropicAgentClient:
    """Agent-loop LLM client using OpenAI-compatible chat-completions API.

    Works with any provider that implements the ``/v1/chat/completions``
    endpoint with function-calling / tool_use support, including
    Kimi (Moonshot), DeepSeek, OpenAI, etc.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str,
        model: str,
        timeout_seconds: float,
        tool_definitions: list[dict[str, Any]],
    ) -> None:
        self.base_url = (base_url or "").strip()
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.tool_definitions = tool_definitions

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.api_key)

    def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        conversation_id: str,
        step: int,
    ) -> AnthropicLLMResponse:
        if not self.enabled:
            raise AnthropicLLMError(message="Agent LLM client is not configured")

        started_at = time.perf_counter()

        openai_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
        ]
        openai_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 4096,
            "messages": openai_messages,
        }
        if self.tool_definitions:
            payload["tools"] = self.tool_definitions
            payload["tool_choice"] = "auto"

        endpoint = _chat_completions_endpoint(self.base_url)

        logger.info(
            "anthropic_llm_request conversation_id=%s step=%s model=%s message_count=%s",
            conversation_id,
            step,
            self.model,
            len(messages),
        )
        logger.info(
            "anthropic_llm_request_debug conversation_id=%s step=%s\n%s",
            conversation_id,
            step,
            format_agent_debug_blocks(
                ai_input={
                    "conversation_id": conversation_id,
                    "step": step,
                    "model": self.model,
                    "system": system[:300] + "..." if len(system) > 300 else system,
                    "messages": messages,
                    "tools": [t["function"]["name"] for t in self.tool_definitions if "function" in t],
                },
            ),
        )

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except TimeoutError as exc:
            self._log_failure(conversation_id=conversation_id, step=step, error=exc, started_at=started_at)
            raise AnthropicLLMError(message="LLM request timed out") from exc
        except socket.timeout as exc:
            self._log_failure(conversation_id=conversation_id, step=step, error=exc, started_at=started_at)
            raise AnthropicLLMError(message="LLM request timed out") from exc
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            self._log_failure(
                conversation_id=conversation_id, step=step, error=exc, started_at=started_at, details=details,
            )
            raise AnthropicLLMError(
                message=f"LLM HTTP error ({exc.code}): {details or exc.reason}",
            ) from exc
        except urllib_error.URLError as exc:
            self._log_failure(conversation_id=conversation_id, step=step, error=exc, started_at=started_at)
            raise AnthropicLLMError(message=f"LLM request failed: {exc.reason}") from exc

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "anthropic_llm_error conversation_id=%s step=%s elapsed_ms=%s error_type=JSONDecodeError error=%s",
                conversation_id, step, elapsed_ms, str(exc),
            )
            raise AnthropicLLMError(message="LLM returned non-JSON response") from exc

        parsed = self._parse_response(data)

        logger.info(
            "anthropic_llm_response conversation_id=%s step=%s elapsed_ms=%s stop_reason=%s tool_calls=%s",
            conversation_id,
            step,
            elapsed_ms,
            parsed.stop_reason,
            len(parsed.tool_calls),
        )
        logger.info(
            "anthropic_llm_response_debug conversation_id=%s step=%s\n%s",
            conversation_id,
            step,
            format_agent_debug_blocks(
                ai_output={
                    "conversation_id": conversation_id,
                    "step": step,
                    "elapsed_ms": elapsed_ms,
                    "stop_reason": parsed.stop_reason,
                    "content": parsed.content[:500] if parsed.content else "",
                    "tool_calls": [
                        {"id": tc.call_id, "name": tc.tool_name, "args": tc.arguments}
                        for tc in parsed.tool_calls
                    ],
                },
                thinking=parsed.thinking or parsed.content,
            ),
        )

        return parsed

    def _parse_response(self, data: dict[str, Any]) -> AnthropicLLMResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AnthropicLLMError(message="LLM response missing choices")

        first = choices[0]
        if not isinstance(first, dict):
            raise AnthropicLLMError(message="LLM choice is not an object")

        finish_reason = str(first.get("finish_reason") or "stop")
        message = first.get("message") or {}
        content = str(message.get("content") or "").strip()

        raw_tool_calls = message.get("tool_calls") or []
        tool_calls: list[AnthropicToolCall] = []
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
                tool_calls.append(AnthropicToolCall(call_id=call_id, tool_name=tool_name, arguments=arguments))

        stop_reason = "tool_use" if tool_calls else finish_reason

        return AnthropicLLMResponse(
            content=content,
            thinking="",
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw_content_blocks=[],
        )

    def _log_failure(
        self,
        *,
        conversation_id: str,
        step: int,
        error: Exception,
        started_at: float,
        details: str | None = None,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.warning(
            "anthropic_llm_error conversation_id=%s step=%s elapsed_ms=%s error_type=%s error=%s",
            conversation_id,
            step,
            elapsed_ms,
            type(error).__name__,
            str(error),
        )
        logger.warning(
            "anthropic_llm_error_debug conversation_id=%s step=%s\n%s",
            conversation_id,
            step,
            format_agent_debug_blocks(
                ai_output={
                    "conversation_id": conversation_id,
                    "step": step,
                    "elapsed_ms": elapsed_ms,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "details": details or "",
                },
            ),
        )


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"
