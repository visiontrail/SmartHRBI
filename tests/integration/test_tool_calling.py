from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from apps.api.chat import clear_chat_stream_service_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from tests.auth_utils import auth_headers


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_chat_stream_service_cache()
    clear_view_storage_service_cache()


def _excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def _upload_dataset(client: TestClient) -> str:
    upload_file = _excel_bytes(
        [
            {"employee id": "E-001", "department": "HR", "status": "active", "salary": 1000},
            {"employee id": "E-002", "department": "HR", "status": "inactive", "salary": 1200},
            {"employee id": "E-003", "department": "PM", "status": "active", "salary": 900},
        ]
    )

    headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
    response = client.post(
        "/datasets/upload",
        data={"user_id": "alice", "project_id": "north"},
        headers=headers,
        files=[
            (
                "files",
                (
                    "employees.xlsx",
                    upload_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )
    assert response.status_code == 200
    return response.json()["dataset_table"]


def test_tool_calling_query_metrics_returns_structured_result(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )
        response = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "conv-1",
                "request_id": "req-1",
                "idempotency_key": "idem-1",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "role": "viewer",
                "department": "HR",
                "clearance": 1,
                "tool": {
                    "name": "query_metrics",
                    "arguments": {
                        "metric": "active_employee_count",
                        "group_by": ["department"],
                    },
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["tool_name"] == "query_metrics"
    assert payload["attempts"] == 1
    assert payload["result"]["metric"] == "active_employee_count"
    assert payload["result"]["rows"] == [{"department": "HR", "metric_value": 1}]


def test_tool_calling_retries_and_uses_idempotency_cache(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        headers = auth_headers(client, user_id="alice", project_id="north", role="viewer")

        first = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "conv-2",
                "request_id": "req-2",
                "idempotency_key": "idem-retry-1",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {
                    "name": "save_view",
                    "arguments": {
                        "title": "retry success",
                        "chart_spec": {"engine": "recharts"},
                        "failure_key": "save-retry",
                        "simulate_retryable_failures": 2,
                    },
                },
            },
            headers=headers,
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["status"] == "success"
        assert first_payload["attempts"] == 3
        assert first_payload["from_cache"] is False

        second = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "conv-2",
                "request_id": "req-2-repeat",
                "idempotency_key": "idem-retry-1",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {
                    "name": "save_view",
                    "arguments": {
                        "title": "retry success",
                        "chart_spec": {"engine": "recharts"},
                        "failure_key": "save-retry",
                        "simulate_retryable_failures": 2,
                    },
                },
            },
            headers=headers,
        )

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["status"] == "success"
    assert second_payload["attempts"] == 3
    assert second_payload["from_cache"] is True
    assert second_payload["result"] == first_payload["result"]


def test_tool_calling_gracefully_fails_after_max_retries(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        headers = auth_headers(client, user_id="alice", project_id="north", role="viewer")
        response = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "conv-3",
                "request_id": "req-3",
                "idempotency_key": "idem-retry-fail",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "retry_limit": 2,
                "tool": {
                    "name": "save_view",
                    "arguments": {
                        "title": "retry fail",
                        "chart_spec": {"engine": "recharts"},
                        "failure_key": "save-retry-fail",
                        "simulate_retryable_failures": 10,
                    },
                },
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["attempts"] == 3
    assert payload["error"]["code"] == "TOOL_RETRY_EXHAUSTED"
