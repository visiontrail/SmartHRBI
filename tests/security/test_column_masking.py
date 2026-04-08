from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from apps.api.audit import clear_audit_logger_cache
from apps.api.auth import clear_auth_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from tests.auth_utils import auth_headers, expect_error_code


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'views.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_auth_cache()
    clear_audit_logger_cache()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_view_storage_service_cache()


def _excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def _upload_dataset(client: TestClient) -> str:
    response = client.post(
        "/datasets/upload",
        data={"user_id": "alice", "project_id": "north"},
        headers=auth_headers(client, user_id="alice", project_id="north", role="admin", clearance=9),
        files=[
            (
                "files",
                (
                    "employees.xlsx",
                    _excel_bytes(
                        [
                            {"employee id": "E-001", "department": "HR", "status": "active", "salary": 1000},
                            {"employee id": "E-002", "department": "PM", "status": "active", "salary": 1500},
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )
    assert response.status_code == 200
    return str(response.json()["dataset_table"])


def test_viewer_querying_salary_metric_is_blocked_without_field_leak(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        viewer_headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )

        response = client.post(
            "/semantic/query",
            headers=viewer_headers,
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "metric": "avg_salary",
                "department": "HR",
            },
        )

    expect_error_code(response, "ACCESS_DENIED", status_code=403)
    assert "salary" not in response.json()["detail"]["message"].lower()


def test_describe_dataset_hides_sensitive_columns_for_viewer(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        viewer_headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )

        response = client.post(
            "/chat/tool-call",
            headers=viewer_headers,
            json={
                "conversation_id": "conv-mask",
                "request_id": "req-mask",
                "idempotency_key": "idem-mask",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {"name": "describe_dataset", "arguments": {"sample_limit": 5}},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    columns = payload["result"]["columns"]
    assert all(item["name"] != "salary" for item in columns)

    sample_rows = payload["result"]["sample_rows"]
    assert sample_rows
    assert all(row.get("salary") == "[REDACTED]" for row in sample_rows)
