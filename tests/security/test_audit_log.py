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


def test_audit_log_captures_login_upload_query_and_denied_events(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        admin_headers = auth_headers(client, user_id="admin", project_id="north", role="admin", clearance=9)

        upload = client.post(
            "/datasets/upload",
            data={"user_id": "admin", "project_id": "north"},
            headers=admin_headers,
            files=[
                (
                    "files",
                    (
                        "employees.xlsx",
                        _excel_bytes([{"Employee ID": "E-001", "Department": "HR", "Salary": 1000}]),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                )
            ],
        )
        assert upload.status_code == 200

        viewer_headers = auth_headers(client, user_id="viewer", project_id="north", role="viewer", clearance=1)
        denied = client.post(
            "/datasets/upload",
            data={"user_id": "viewer", "project_id": "north"},
            headers=viewer_headers,
            files=[
                (
                    "files",
                    (
                        "employees-viewer.xlsx",
                        _excel_bytes([{"Employee ID": "E-002", "Department": "PM", "Salary": 900}]),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                )
            ],
        )
        expect_error_code(denied, "RBAC_FORBIDDEN", status_code=403)

        events_response = client.get(
            "/audit/events",
            headers=admin_headers,
            params={"limit": 50},
        )
        assert events_response.status_code == 200

        events_payload = events_response.json()
        assert events_payload["count"] >= 4
        events = events_payload["events"]

    actions = {item["action"] for item in events}
    assert "login" in actions
    assert "upload" in actions
    assert "datasets:upload" in actions

    denied_events = [item for item in events if item["status"] == "denied"]
    assert denied_events
    assert any(item["severity"] == "ALERT" for item in denied_events)


def test_audit_log_endpoint_requires_privileged_role(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        viewer_headers = auth_headers(client, user_id="viewer", project_id="north", role="viewer", clearance=1)
        response = client.get("/audit/events", headers=viewer_headers)

    expect_error_code(response, "RBAC_FORBIDDEN", status_code=403)
