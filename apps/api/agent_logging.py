from __future__ import annotations

import json
from typing import Any

_SECTION_INPUT = "==============="
_SECTION_OUTPUT = "+++++++++++++++"
_SECTION_TOOLS = "####################"
_SECTION_TOOL_RESULT = "@@@@@@@@@@@@@@"
_SECTION_THINKING = "********************"
_MAX_SECTION_CHARS = 24000


def format_agent_debug_blocks(
    *,
    ai_input: Any = None,
    ai_output: Any = None,
    tool_trace: Any = None,
    tool_result: Any = None,
    thinking: Any = None,
) -> str:
    sections: list[str] = []
    _append_section(sections=sections, title="输入AI的内容", separator=_SECTION_INPUT, value=ai_input)
    _append_section(sections=sections, title="AI输出的内容", separator=_SECTION_OUTPUT, value=ai_output)
    _append_section(sections=sections, title="AI调用的工具", separator=_SECTION_TOOLS, value=tool_trace)
    _append_section(sections=sections, title="工具返回给AI的结果", separator=_SECTION_TOOL_RESULT, value=tool_result)
    _append_section(sections=sections, title="Thinking内容", separator=_SECTION_THINKING, value=thinking)
    return "\n\n".join(sections)


def _append_section(*, sections: list[str], title: str, separator: str, value: Any) -> None:
    rendered = _render_section(value)
    if rendered is None:
        return
    sections.append("\n".join([separator, title, rendered, separator]))


def _render_section(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return _truncate(text)

    if isinstance(value, (list, dict, tuple)):
        if not value:
            return None
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            text = str(value)
        return _truncate(text)

    if isinstance(value, (int, float, bool)):
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            text = str(value)
        return _truncate(text)

    text = str(value).strip()
    if not text:
        return None
    return _truncate(text)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_SECTION_CHARS:
        return text
    remaining = len(text) - _MAX_SECTION_CHARS
    return f"{text[:_MAX_SECTION_CHARS]}\n...<truncated {remaining} chars>"
