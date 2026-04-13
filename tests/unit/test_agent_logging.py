from __future__ import annotations

from apps.api.agent_logging import format_agent_debug_blocks


def test_format_agent_debug_blocks_skips_empty_sections() -> None:
    text = format_agent_debug_blocks(ai_input=None, ai_output="", tool_trace=[], thinking="  ")
    assert text == ""


def test_format_agent_debug_blocks_keeps_non_empty_sections_only() -> None:
    text = format_agent_debug_blocks(ai_input={"q": "test"}, ai_output="ok", tool_trace=None, thinking=None)
    assert "输入AI的内容" in text
    assert "AI输出的内容" in text
    assert "AI调用的工具" not in text
    assert "工具返回给AI的结果" not in text
    assert "Thinking内容" not in text
    assert "(empty)" not in text


def test_format_agent_debug_blocks_uses_different_markers_for_tool_call_and_result() -> None:
    text = format_agent_debug_blocks(
        tool_trace={"tool_name": "list_tables", "arguments": {}},
        tool_result={"tool_name": "list_tables", "status": "success", "result": {"count": 1}},
    )
    assert "####################\nAI调用的工具" in text
    assert "@@@@@@@@@@@@@@\n工具返回给AI的结果" in text
