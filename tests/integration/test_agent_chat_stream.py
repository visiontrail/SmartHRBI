from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app
from tests.agent_test_utils import read_sse_events, set_agent_env, upload_dataset
from tests.auth_utils import auth_headers


def test_agent_chat_stream_emits_planning_tool_trace_spec_and_final(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR", "hire_year": 2022},
                {"employee_id": "E-002", "department": "HR", "hire_year": 2023},
                {"employee_id": "E-003", "department": "PM", "hire_year": 2023},
            ],
            user_id="admin",
            role="admin",
            department="HR",
            clearance=9,
        )
        headers = auth_headers(
            client,
            user_id="admin",
            project_id="north",
            role="admin",
            department="HR",
            clearance=9,
        )

        start = time.perf_counter()
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "agent-chat-stream-conv-1",
                "request_id": "agent-chat-stream-req-1",
                "user_id": "admin",
                "project_id": "north",
                "dataset_table": dataset_table,
                "message": "柱状图显示入职年份统计",
            },
            headers=headers,
        ) as response:
            assert response.status_code == 200
            events, first_chunk_at = read_sse_events(response)

    assert first_chunk_at is not None
    assert first_chunk_at - start < 2.0
    event_names = [item["event"] for item in events]
    assert "planning" in event_names
    assert "tool_use" in event_names
    assert "tool_result" in event_names
    assert event_names[-2:] == ["spec", "final"]
    final_payload = events[-1]["data"]
    assert final_payload["status"] == "completed"
    assert final_payload["tool_steps"] >= 3
    spec_payload = events[-2]["data"]
    assert spec_payload["spec"]["chart_type"] == "bar"


def test_agent_chat_stream_replays_agent_events(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR", "hire_year": 2022},
                {"employee_id": "E-002", "department": "HR", "hire_year": 2023},
            ],
            user_id="admin",
            role="admin",
            department="HR",
            clearance=9,
        )
        headers = auth_headers(
            client,
            user_id="admin",
            project_id="north",
            role="admin",
            department="HR",
            clearance=9,
        )

        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "agent-chat-stream-conv-2",
                "request_id": "agent-chat-stream-req-2",
                "user_id": "admin",
                "project_id": "north",
                "dataset_table": dataset_table,
                "message": "柱状图显示入职年份统计",
            },
            headers=headers,
        ) as first_response:
            assert first_response.status_code == 200
            first_events, _ = read_sse_events(first_response)

        replay_from = first_events[2]["id"]
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "agent-chat-stream-conv-2",
                "request_id": "agent-chat-stream-req-2-replay",
                "user_id": "admin",
                "project_id": "north",
                "dataset_table": dataset_table,
                "message": None,
                "last_event_id": replay_from,
            },
            headers=headers,
        ) as replay_response:
            assert replay_response.status_code == 200
            replay_events, _ = read_sse_events(replay_response)

    assert replay_events
    assert replay_events[0]["id"] == replay_from + 1
    assert replay_events[-1]["event"] == "final"


def test_agent_primary_does_not_fallback_to_deterministic_on_runtime_failure(
    monkeypatch, tmp_path: Path
) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR"},
                {"employee_id": "E-002", "department": "PM"},
            ],
            user_id="admin",
            role="admin",
            department="HR",
            clearance=9,
        )
        headers = auth_headers(
            client,
            user_id="admin",
            project_id="north",
            role="admin",
            department="HR",
            clearance=9,
        )

        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "agent-chat-stream-conv-no-fallback",
                "request_id": "agent-chat-stream-req-no-fallback",
                "user_id": "admin",
                "project_id": "north",
                "dataset_table": dataset_table,
                "message": "画一个福利等级热力图",
            },
            headers=headers,
        ) as response:
            assert response.status_code == 200
            events, _ = read_sse_events(response)

    assert [item["event"] for item in events] == ["error", "final"]
    assert events[0]["data"]["status"] == "failed"
    assert events[-1]["data"]["status"] == "failed"
