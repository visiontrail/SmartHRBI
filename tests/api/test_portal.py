from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.audit import clear_audit_logger_cache
from apps.api.auth import clear_auth_cache
from apps.api.chat import clear_chat_stream_service_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.published_pages import clear_published_page_store_cache
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from apps.api.workspaces import clear_workspace_service_cache
from apps.api.main import app
from tests.auth_utils import auth_headers, expect_error_code


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'workspace-state.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AGENT_MAX_SQL_ROWS", "1")
    get_settings.cache_clear()
    clear_auth_cache()
    clear_audit_logger_cache()
    clear_chat_stream_service_cache()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_view_storage_service_cache()
    clear_workspace_service_cache()
    clear_published_page_store_cache()


def test_publish_workspace_writes_snapshot_and_serves_portal_assets(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north", role="viewer", clearance=1)
        workspace_response = client.post("/workspaces", json={"name": "Portal Workspace"}, headers=headers)
        assert workspace_response.status_code == 200
        workspace_id = workspace_response.json()["workspace_id"]

        publish_response = client.post(
            f"/workspaces/{workspace_id}/publish",
            headers=headers,
            json={
                "layout": {
                    "grid": {"columns": 3, "rows": [{"id": "row-1", "height": 400}]},
                    "zones": [{"id": "zone-1", "chart_id": "headcount"}],
                },
                "sidebar": [{"id": "overview", "label": "Overview", "anchor": "row-1"}],
                "charts": [
                    {
                        "chart_id": "headcount",
                        "title": "Headcount",
                        "chart_type": "bar",
                        "spec": {"chart_type": "bar", "title": "Headcount"},
                        "rows": [
                            {"department": "HR", "headcount": 4, "salary": 100},
                            {"department": "Finance", "headcount": 3, "salary": 120},
                        ],
                    }
                ],
            },
        )
        assert publish_response.status_code == 200
        publish_payload = publish_response.json()
        assert publish_payload["version"] == 1
        page_id = publish_payload["published_page_id"]

        history_response = client.get(f"/workspaces/{workspace_id}/published", headers=headers)
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert history_payload["count"] == 1
        assert history_payload["published_pages"][0]["page_id"] == page_id

        portal_workspaces_response = client.get("/portal/workspaces")
        assert portal_workspaces_response.status_code == 200
        portal_workspaces = portal_workspaces_response.json()
        assert portal_workspaces["count"] == 1
        assert portal_workspaces["workspaces"][0]["latest_page_id"] == page_id
        assert portal_workspaces["workspaces"][0]["name"] == "Portal Workspace"

        manifest_response = client.get(f"/portal/pages/{page_id}/manifest")
        assert manifest_response.status_code == 200
        manifest = manifest_response.json()["manifest"]
        assert manifest["workspace_id"] == workspace_id
        assert manifest["charts"][0]["data_truncated"] is True

        chart_response = client.get(f"/portal/pages/{page_id}/charts/headcount/data")
        assert chart_response.status_code == 200
        chart_payload = chart_response.json()
        assert chart_payload["data_truncated"] is True
        assert chart_payload["rows"] == [{"department": "HR", "headcount": 4}]


def test_publish_rejects_chart_without_rows(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north", role="viewer", clearance=1)
        workspace_response = client.post("/workspaces", json={"name": "Blocked Publish"}, headers=headers)
        assert workspace_response.status_code == 200
        workspace_id = workspace_response.json()["workspace_id"]

        publish_response = client.post(
            f"/workspaces/{workspace_id}/publish",
            headers=headers,
            json={"charts": [{"chart_id": "empty", "spec": {}, "rows": []}]},
        )
        expect_error_code(publish_response, "PUBLISH_CHART_DATA_REQUIRED", status_code=422)


def test_portal_missing_page_returns_404(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.get("/portal/pages/missing/manifest")
        expect_error_code(response, "PUBLISHED_PAGE_NOT_FOUND", status_code=404)
