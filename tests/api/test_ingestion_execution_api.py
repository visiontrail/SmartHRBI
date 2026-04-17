from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd
from fastapi.testclient import TestClient

from apps.api.agentic_ingestion.runtime import WriteIngestionAgentRuntime
from apps.api.agentic_ingestion.uploads import clear_ingestion_upload_service_cache
from apps.api.audit import clear_audit_logger_cache
from apps.api.auth import clear_auth_cache
from apps.api.chat import clear_chat_stream_service_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
from apps.api.table_catalog import clear_table_catalog_service_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from apps.api.workspaces import clear_workspace_service_cache
from tests.auth_utils import auth_headers, expect_error_code


def _set_minimal_env(monkeypatch, tmp_path: Path, *, ingestion_enabled: bool) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'workspace-state.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AI_API_KEY", "test-ai-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AGENTIC_INGESTION_ENABLED", "true" if ingestion_enabled else "false")

    def _mock_infer_business_type_with_llm(
        self,
        *,
        file_name: str,
        columns: list[str],
        sheet_names: list[str],
        sample_preview: list[object],
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, object]:
        _ = (self, file_name, columns, sheet_names, sample_preview, model, base_url, api_key, timeout_seconds)
        return {
            "business_type": "roster",
            "confidence": 0.9,
            "reasoning": "mocked llm classification",
        }

    monkeypatch.setattr(
        WriteIngestionAgentRuntime,
        "_infer_business_type_with_llm",
        _mock_infer_business_type_with_llm,
    )

    get_settings.cache_clear()
    clear_auth_cache()
    clear_audit_logger_cache()
    clear_chat_stream_service_cache()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_view_storage_service_cache()
    clear_workspace_service_cache()
    clear_table_catalog_service_cache()
    clear_ingestion_upload_service_cache()


def _excel_bytes() -> bytes:
    roster = pd.DataFrame(
        [
            {"Employee ID": "E-001", "Name": "Alice", "Department": "HR"},
            {"Employee ID": "E-002", "Name": "Bob", "Department": "PM"},
            {"Employee ID": "E-003", "Name": "Cathy", "Department": "Finance"},
        ]
    )

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        roster.to_excel(writer, index=False, sheet_name="Roster")
    return buffer.getvalue()


def _upload_file_payload() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "files",
            (
                "roster.xlsx",
                _excel_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
    ]


def _create_workspace(client: TestClient, headers: dict[str, str], *, name: str) -> str:
    response = client.post("/workspaces", json={"name": name}, headers=headers)
    assert response.status_code == 200
    return response.json()["workspace_id"]


def _create_upload(client: TestClient, headers: dict[str, str], *, workspace_id: str) -> dict[str, str]:
    response = client.post(
        "/ingestion/uploads",
        data={"workspace_id": workspace_id},
        headers=headers,
        files=_upload_file_payload(),
    )
    assert response.status_code == 200
    return response.json()


def _prepare_approval_job(
    client: TestClient,
    headers: dict[str, str],
    *,
    workspace_id: str,
) -> tuple[str, str]:
    catalog_response = client.post(
        f"/workspaces/{workspace_id}/catalog",
        headers=headers,
        json={
            "table_name": "employee_roster",
            "human_label": "Employee Roster",
            "business_type": "roster",
            "write_mode": "update_existing",
            "time_grain": "none",
            "primary_keys": ["employee_id"],
            "match_columns": ["employee_id"],
            "is_active_target": True,
            "description": "Primary roster table",
        },
    )
    assert catalog_response.status_code == 200

    upload_payload = _create_upload(client, headers, workspace_id=workspace_id)
    job_id = upload_payload["job_id"]
    plan_response = client.post(
        "/ingestion/plan",
        json={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "conversation_id": "conv-exec-1",
            "message": "请更新花名册",
        },
        headers=headers,
    )
    assert plan_response.status_code == 200
    plan_payload = plan_response.json()
    assert plan_payload["status"] == "awaiting_user_approval"
    return job_id, plan_payload["proposal_id"]


def test_ingestion_approve_and_execute_persist_receipt(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path, ingestion_enabled=True)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
        workspace_id = _create_workspace(client, owner_headers, name="Execution Workspace")
        job_id, proposal_id = _prepare_approval_job(client, owner_headers, workspace_id=workspace_id)

        approve_response = client.post(
            "/ingestion/approve",
            json={
                "workspace_id": workspace_id,
                "job_id": job_id,
                "proposal_id": proposal_id,
                "approved_action": "update_existing",
            },
            headers=owner_headers,
        )
        assert approve_response.status_code == 200
        approve_payload = approve_response.json()
        assert approve_payload["status"] == "approved"
        assert approve_payload["target_table"] == "employee_roster"
        assert approve_payload["dry_run_summary"]["predicted_affected_rows"] >= 0

        execute_response = client.post(
            "/ingestion/execute",
            json={
                "workspace_id": workspace_id,
                "job_id": job_id,
                "proposal_id": proposal_id,
            },
            headers=owner_headers,
        )

    assert execute_response.status_code == 200
    execute_payload = execute_response.json()
    assert execute_payload["status"] == "succeeded"
    assert execute_payload["execution_id"]
    assert execute_payload["receipt"]["success"] is True
    assert execute_payload["receipt"]["target_table"] == "employee_roster"

    db_path = tmp_path / "workspace-state.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        job_row = conn.execute(
            "SELECT status FROM ingestion_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert job_row is not None
        assert str(job_row["status"]) == "succeeded"

        execution_row = conn.execute(
            """
            SELECT status, execution_mode, execution_receipt
            FROM ingestion_executions
            WHERE id = ?
            """,
            (execute_payload["execution_id"],),
        ).fetchone()
        assert execution_row is not None
        assert str(execution_row["status"]) == "succeeded"
        assert str(execution_row["execution_mode"]) == "update_existing"

        event_rows = conn.execute(
            "SELECT event_type FROM ingestion_events WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        event_types = {str(item["event_type"]) for item in event_rows}
        assert "proposal_approved" in event_types
        assert "execution_succeeded" in event_types

    duckdb_path = Path(execute_payload["receipt"]["duckdb_path"])
    assert duckdb_path.exists()
    conn = duckdb.connect(str(duckdb_path))
    try:
        count = int(conn.execute("SELECT COUNT(*) FROM employee_roster").fetchone()[0])
    finally:
        conn.close()
    assert count > 0


def test_ingestion_execute_requires_approval(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path, ingestion_enabled=True)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
        workspace_id = _create_workspace(client, owner_headers, name="Execution Guard Workspace")
        job_id, proposal_id = _prepare_approval_job(client, owner_headers, workspace_id=workspace_id)

        execute_response = client.post(
            "/ingestion/execute",
            json={
                "workspace_id": workspace_id,
                "job_id": job_id,
                "proposal_id": proposal_id,
            },
            headers=owner_headers,
        )

    expect_error_code(execute_response, "INGESTION_EXECUTION_NOT_ALLOWED", status_code=409)


def test_ingestion_approve_workspace_role_guard(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path, ingestion_enabled=True)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
        viewer_headers = auth_headers(client, user_id="bob", project_id="north", role="hr")
        workspace_id = _create_workspace(client, owner_headers, name="Execution Role Guard")
        add_member_response = client.post(
            f"/workspaces/{workspace_id}/members",
            headers=owner_headers,
            json={"user_id": "bob", "role": "viewer", "display_name": "Bob Viewer"},
        )
        assert add_member_response.status_code == 200

        job_id, proposal_id = _prepare_approval_job(client, owner_headers, workspace_id=workspace_id)
        approve_response = client.post(
            "/ingestion/approve",
            json={
                "workspace_id": workspace_id,
                "job_id": job_id,
                "proposal_id": proposal_id,
                "approved_action": "update_existing",
            },
            headers=viewer_headers,
        )

    expect_error_code(approve_response, "WORKSPACE_FORBIDDEN", status_code=403)


def test_ingestion_approve_respects_feature_flag(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path, ingestion_enabled=False)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
        workspace_id = _create_workspace(client, owner_headers, name="Execution Flag Guard")
        response = client.post(
            "/ingestion/approve",
            json={
                "workspace_id": workspace_id,
                "job_id": "job-demo",
                "proposal_id": "proposal-demo",
                "approved_action": "update_existing",
            },
            headers=owner_headers,
        )

    expect_error_code(response, "AGENTIC_INGESTION_DISABLED", status_code=404)
