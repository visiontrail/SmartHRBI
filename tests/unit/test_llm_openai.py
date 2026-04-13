from __future__ import annotations

import json
import logging

import pytest

from apps.api.llm_openai import OpenAIAgentLoopClient, OpenAICompatibleToolSelector, ToolSelectionError


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        _ = (exc_type, exc, tb)

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_openai_selector_hits_chat_completions_endpoint_and_parses_payload(monkeypatch, caplog) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = request.data.decode("utf-8")
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "tool": "query_metrics",
                                    "arguments": {
                                        "metric": "headcount_total",
                                        "group_by": ["department"],
                                        "limit": 20,
                                    },
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("apps.api.llm_openai.urllib_request.urlopen", fake_urlopen)

    selector = OpenAICompatibleToolSelector(
        base_url="https://custom-llm.example.com",
        api_key="test-api-key",
        model="gpt-4o-mini",
        timeout_seconds=8.0,
        metric_catalog=[{"name": "headcount_total", "synonyms": ["headcount"]}],
    )

    with caplog.at_level(logging.INFO, logger="smarthrbi.llm"):
        selected = selector.select_tool(
            message="按部门看人数",
            conversation_id="conv-001",
            context={},
        )

    assert captured["url"] == "https://custom-llm.example.com/v1/chat/completions"
    assert captured["timeout"] == 8.0
    assert captured["auth"] == "Bearer test-api-key"
    assert selected.tool_name == "query_metrics"
    assert selected.arguments["metric"] == "headcount_total"
    assert selected.arguments["group_by"] == ["department"]
    assert selected.arguments["limit"] == 20

    posted = json.loads(str(captured["body"]))
    assert posted["model"] == "gpt-4o-mini"
    assert posted["messages"][0]["role"] == "system"
    assert "llm_tool_selector_request" in caplog.text
    assert "llm_tool_selector_response" in caplog.text
    assert '\\"conversation_id\\": \\"conv-001\\"' in caplog.text
    assert '\\"message\\": \\"按部门看人数\\"' in caplog.text
    assert "输入AI的内容" in caplog.text
    assert "AI输出的内容" in caplog.text
    assert "Thinking内容" in caplog.text


def test_openai_selector_drops_unknown_metric_and_falls_back_to_intent(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        _ = (request, timeout)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {"tool": "query_metrics", "arguments": {"metric": "unknown_metric", "group_by": ["department"]}}
                            """
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("apps.api.llm_openai.urllib_request.urlopen", fake_urlopen)

    selector = OpenAICompatibleToolSelector(
        base_url="https://custom-llm.example.com/v1",
        api_key="test-api-key",
        model="qwen-plus",
        timeout_seconds=6.0,
        metric_catalog=[{"name": "attrition_rate", "synonyms": []}],
    )

    selected = selector.select_tool(
        message="按部门看在职人数",
        conversation_id="conv-002",
        context={},
    )

    assert selected.tool_name == "query_metrics"
    assert "metric" not in selected.arguments
    assert selected.arguments["intent"] == "按部门看在职人数"
    assert selected.arguments["group_by"] == ["department"]


def test_openai_selector_reroutes_custom_distribution_requests_to_describe_dataset(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        _ = (request, timeout)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "tool": "query_metrics",
                                    "arguments": {"intent": "柱状图显示薪资分布统计"},
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("apps.api.llm_openai.urllib_request.urlopen", fake_urlopen)

    selector = OpenAICompatibleToolSelector(
        base_url="https://custom-llm.example.com/v1",
        api_key="test-api-key",
        model="qwen-plus",
        timeout_seconds=6.0,
        metric_catalog=[{"name": "avg_salary", "synonyms": ["平均薪资"]}],
    )

    selected = selector.select_tool(
        message="柱状图显示薪资分布统计",
        conversation_id="conv-003",
        context={},
    )

    assert selected.tool_name == "describe_dataset"
    assert selected.arguments == {"sample_limit": 10}


def test_openai_selector_wraps_timeout_as_tool_selection_error(monkeypatch, caplog) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        _ = (request, timeout)
        raise TimeoutError("timed out")

    monkeypatch.setattr("apps.api.llm_openai.urllib_request.urlopen", fake_urlopen)

    selector = OpenAICompatibleToolSelector(
        base_url="https://custom-llm.example.com/v1",
        api_key="test-api-key",
        model="qwen-plus",
        timeout_seconds=6.0,
        metric_catalog=[{"name": "attrition_rate", "synonyms": []}],
    )

    with caplog.at_level(logging.WARNING, logger="smarthrbi.llm"):
        with pytest.raises(ToolSelectionError, match="timed out"):
            selector.select_tool(
                message="Hi",
                conversation_id="conv-timeout",
                context={},
            )

    assert "llm_tool_selector_error" in caplog.text
    assert "error_type=TimeoutError" in caplog.text
    assert "timeout_seconds=6.0" in caplog.text
    assert '\\"conversation_id\\": \\"conv-timeout\\"' in caplog.text
    assert '\\"message\\": \\"Hi\\"' in caplog.text
    assert "输入AI的内容" in caplog.text
    assert "AI输出的内容" in caplog.text
    assert "Thinking内容" in caplog.text


def test_agent_loop_client_logs_request_response_and_thinking(monkeypatch, caplog) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        _ = (request, timeout)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "先检查表结构，再查询年份分布。",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "describe_table",
                                        "arguments": json.dumps({"table": "dataset_demo"}, ensure_ascii=False),
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr("apps.api.llm_openai.urllib_request.urlopen", fake_urlopen)

    client = OpenAIAgentLoopClient(
        base_url="https://custom-llm.example.com",
        api_key="test-api-key",
        model="gpt-4o-mini",
        timeout_seconds=8.0,
        tool_definitions=[
            {
                "type": "function",
                "function": {
                    "name": "describe_table",
                    "description": "Inspect a table",
                    "parameters": {"type": "object", "properties": {"table": {"type": "string"}}},
                },
            }
        ],
    )

    with caplog.at_level(logging.INFO, logger="smarthrbi.llm"):
        response = client.chat(
            messages=[{"role": "user", "content": "柱状图显示入职年份统计"}],
            conversation_id="conv-agent-log",
            step=1,
        )

    assert response.finish_reason == "tool_calls"
    assert response.content == "先检查表结构，再查询年份分布。"
    assert response.tool_calls[0].tool_name == "describe_table"
    assert response.tool_calls[0].arguments == {"table": "dataset_demo"}
    assert "agent_llm_request_debug" in caplog.text
    assert "agent_llm_response_debug" in caplog.text
    assert '"conversation_id": "conv-agent-log"' in caplog.text
    assert '"tool_name": "describe_table"' in caplog.text
    assert "先检查表结构，再查询年份分布。" in caplog.text
    assert "输入AI的内容" in caplog.text
    assert "AI输出的内容" in caplog.text
    assert "Thinking内容" in caplog.text
