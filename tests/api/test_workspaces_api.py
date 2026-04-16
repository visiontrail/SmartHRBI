from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.audit import clear_audit_logger_cache
from apps.api.auth import clear_auth_cache
from apps.api.chat import clear_chat_stream_service_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from apps.api.workspaces import clear_workspace_service_cache
from tests.auth_utils import auth_headers, expect_error_code


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'workspace-state.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_auth_cache()
    clear_audit_logger_cache()
    clear_chat_stream_service_cache()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_view_storage_service_cache()
    clear_workspace_service_cache()


def test_create_and_list_workspaces(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="hr", clearance=5)

        create_response = client.post(
            "/workspaces",
            json={"name": "North Team Workspace"},
            headers=owner_headers,
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["name"] == "North Team Workspace"
        assert created["role"] == "owner"

        list_response = client.get("/workspaces", headers=owner_headers)
        assert list_response.status_code == 200
        listed = list_response.json()
        assert listed["count"] == 1
        assert listed["workspaces"][0]["workspace_id"] == created["workspace_id"]

        members_response = client.get(
            f"/workspaces/{created['workspace_id']}/members",
            headers=owner_headers,
        )
        assert members_response.status_code == 200
        members_payload = members_response.json()
        assert members_payload["count"] == 1
        assert members_payload["members"][0]["user_id"] == "alice"
        assert members_payload["members"][0]["role"] == "owner"


def test_non_member_cannot_access_workspace_resources(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin", clearance=9)
        outsider_headers = auth_headers(client, user_id="bob", project_id="north", role="pm", clearance=5)

        create_response = client.post(
            "/workspaces",
            json={"name": "Restricted Workspace"},
            headers=owner_headers,
        )
        assert create_response.status_code == 200
        workspace_id = create_response.json()["workspace_id"]

        workspace_response = client.get(f"/workspaces/{workspace_id}", headers=outsider_headers)
        expect_error_code(workspace_response, "WORKSPACE_FORBIDDEN", status_code=403)

        chat_response = client.post(
            "/chat/stream",
            headers=outsider_headers,
            json={
                "user_id": "bob",
                "project_id": "north",
                "workspace_id": workspace_id,
                "dataset_table": "employees_wide",
                "message": "hello",
            },
        )
        expect_error_code(chat_response, "WORKSPACE_FORBIDDEN", status_code=403)


def test_owner_can_add_member_and_member_can_bind_chat_workspace(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin", clearance=9)
        member_headers = auth_headers(client, user_id="bob", project_id="north", role="viewer", clearance=1)

        create_response = client.post(
            "/workspaces",
            json={"name": "Shared Workspace"},
            headers=owner_headers,
        )
        assert create_response.status_code == 200
        workspace_id = create_response.json()["workspace_id"]

        add_member_response = client.post(
            f"/workspaces/{workspace_id}/members",
            headers=owner_headers,
            json={"user_id": "bob", "role": "viewer", "display_name": "Bob Viewer"},
        )
        assert add_member_response.status_code == 200
        assert add_member_response.json()["role"] == "viewer"

        member_workspace_response = client.get(f"/workspaces/{workspace_id}", headers=member_headers)
        assert member_workspace_response.status_code == 200
        assert member_workspace_response.json()["workspace_id"] == workspace_id

        chat_response = client.post(
            "/chat/stream",
            headers=member_headers,
            json={
                "user_id": "bob",
                "project_id": "north",
                "workspace_id": workspace_id,
                "dataset_table": "employees_wide",
                "message": None,
            },
        )
        assert chat_response.status_code == 200
        assert "text/event-stream" in chat_response.headers.get("content-type", "")


def test_viewer_cannot_manage_workspace_members(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        owner_headers = auth_headers(client, user_id="alice", project_id="north", role="admin", clearance=9)
        viewer_headers = auth_headers(client, user_id="bob", project_id="north", role="viewer", clearance=1)

        create_response = client.post(
            "/workspaces",
            json={"name": "Role Guard Workspace"},
            headers=owner_headers,
        )
        assert create_response.status_code == 200
        workspace_id = create_response.json()["workspace_id"]

        owner_add_viewer = client.post(
            f"/workspaces/{workspace_id}/members",
            headers=owner_headers,
            json={"user_id": "bob", "role": "viewer"},
        )
        assert owner_add_viewer.status_code == 200

        viewer_add_member = client.post(
            f"/workspaces/{workspace_id}/members",
            headers=viewer_headers,
            json={"user_id": "carol", "role": "viewer"},
        )
        expect_error_code(viewer_add_member, "RBAC_FORBIDDEN", status_code=403)
