from __future__ import annotations

from pathlib import Path

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


def test_legacy_dataset_upload_route_is_removed_for_all_roles(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north", role="viewer", clearance=1)
        response = client.post(
            "/datasets/upload",
            data={"user_id": "alice", "project_id": "north"},
            headers=headers,
            files=[("files", ("employees.xlsx", b"not-used", "application/octet-stream"))],
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


def test_role_change_takes_effect_immediately_for_existing_token(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        user_headers = auth_headers(client, user_id="bob", project_id="north", role="pm", clearance=5)
        admin_headers = auth_headers(client, user_id="admin", project_id="north", role="admin", clearance=9)

        update_role = client.post(
            "/auth/roles/bob",
            json={"role": "viewer", "department": "HR", "clearance": 1},
            headers=admin_headers,
        )
        assert update_role.status_code == 200

        denied = client.post(
            "/auth/roles/alice",
            json={"role": "admin", "department": "HR", "clearance": 9},
            headers=user_headers,
        )

    expect_error_code(denied, "RBAC_FORBIDDEN", status_code=403)
