from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.chat import get_chat_stream_service
from apps.api.main import app
from tests.agent_test_utils import read_sse_events, set_agent_env, upload_dataset
from tests.auth_utils import auth_headers


def test_chat_engine_shadow_keeps_deterministic_response_and_stores_shadow_trace(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_shadow")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR", "hire_year": 2022, "status": "active"},
                {"employee_id": "E-002", "department": "HR", "hire_year": 2023, "status": "active"},
            ],
        )
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "chat-engine-shadow-conv",
                "request_id": "chat-engine-shadow-req",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "message": "按部门看在职人数",
            },
            headers=headers,
        ) as response:
            assert response.status_code == 200
            events, _ = read_sse_events(response)

    assert [item["event"] for item in events] == ["reasoning", "tool", "spec", "final"]
    shadow_context = get_chat_stream_service().sessions.get_context(
        conversation_id="chat-engine-shadow-conv"
    )
    assert shadow_context["shadow_agent_events"]


def test_chat_engine_allowlist_can_force_deterministic_fallback(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(
        monkeypatch,
        tmp_path,
        chat_engine="agent_primary",
        chat_engine_users="allowlisted-user",
    )

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR", "hire_year": 2022, "status": "active"},
                {"employee_id": "E-002", "department": "HR", "hire_year": 2023, "status": "active"},
            ],
        )
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "chat-engine-switch-conv",
                "request_id": "chat-engine-switch-req",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "message": "按部门看在职人数",
            },
            headers=headers,
        ) as response:
            assert response.status_code == 200
            events, _ = read_sse_events(response)

    assert [item["event"] for item in events] == ["reasoning", "tool", "spec", "final"]
