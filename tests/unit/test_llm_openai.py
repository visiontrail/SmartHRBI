from __future__ import annotations

import json
import logging

import pytest

from apps.api.llm_openai import OpenAICompatibleToolSelector, ToolSelectionError


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
