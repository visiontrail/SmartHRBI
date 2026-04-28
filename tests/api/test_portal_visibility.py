from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _setup_env(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / "state.db"}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "portal-vis-secret-key")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("USER_ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("PASSWORD_MIN_LENGTH", "8")
    monkeypatch.setenv("ACCESS_TOKEN_TTL_MIN", "120")
    monkeypatch.setenv("INVITE_LINK_TTL_DAYS", "14")
    monkeypatch.setenv("LEGACY_SERVICE_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_EMAIL", "")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setenv("APP_URL", "http://localhost:3000")


@pytest.fixture()
def client(monkeypatch: Any, tmp_path: Path) -> TestClient:
    _setup_env(monkeypatch, tmp_path)

    from apps.api.config import get_settings
    from apps.api.workspaces import clear_workspace_service_cache
    from apps.api.published_pages import clear_published_page_store_cache
    from apps.api.auth import clear_auth_cache

    get_settings.cache_clear()
    clear_workspace_service_cache()
    clear_published_page_store_cache()
    clear_auth_cache()

    from apps.api.db_migrations import apply_migrations
    apply_migrations()

    from apps.api.main import app
    return TestClient(app, raise_server_exceptions=True)


def _reg(client: TestClient, email: str) -> tuple[str, str]:
    resp = client.post("/auth/register", json={
        "email": email, "password": "password123",
        "display_name": "User", "job_id": 1,
    })
    d = resp.json()
    return d["user"]["id"], d["access_token"]


def _pub(client: TestClient, token: str, ws_id: str, mode: str = "private") -> str:
    resp = client.post(f"/workspaces/{ws_id}/publish", json={
        "layout": {}, "sidebar": [],
        "charts": [{"chart_id": "c1", "spec": {}, "rows": [{"x": 1}]}],
        "visibility_mode": mode,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.json()
    return resp.json()["published_page_id"]


def test_portal_requires_auth(client: TestClient) -> None:
    resp = client.get("/portal/workspaces")
    assert resp.status_code == 401


def test_owner_sees_own_private_workspace(client: TestClient) -> None:
    uid, token = _reg(client, "privowner@example.com")
    resp = client.post("/workspaces", json={"name": "PrivWS"}, headers={"Authorization": f"Bearer {token}"})
    ws_id = resp.json()["workspace_id"]
    page_id = _pub(client, token, ws_id, "private")

    resp2 = client.get("/portal/workspaces", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    ws_ids = [w["workspace_id"] for w in resp2.json()["workspaces"]]
    assert ws_id in ws_ids


def test_non_member_cannot_see_private(client: TestClient) -> None:
    uid1, token1 = _reg(client, "owner_priv@example.com")
    uid2, token2 = _reg(client, "viewer_priv@example.com")

    resp = client.post("/workspaces", json={"name": "HiddenWS"}, headers={"Authorization": f"Bearer {token1}"})
    ws_id = resp.json()["workspace_id"]
    page_id = _pub(client, token1, ws_id, "private")

    resp2 = client.get("/portal/workspaces", headers={"Authorization": f"Bearer {token2}"})
    ws_ids = [w["workspace_id"] for w in resp2.json()["workspaces"]]
    assert ws_id not in ws_ids


def test_registered_mode_visible_to_any_user(client: TestClient) -> None:
    uid1, token1 = _reg(client, "owner_reg2@example.com")
    uid2, token2 = _reg(client, "viewer_reg2@example.com")

    resp = client.post("/workspaces", json={"name": "RegWS"}, headers={"Authorization": f"Bearer {token1}"})
    ws_id = resp.json()["workspace_id"]
    page_id = _pub(client, token1, ws_id, "registered")

    resp2 = client.get("/portal/workspaces", headers={"Authorization": f"Bearer {token2}"})
    ws_ids = [w["workspace_id"] for w in resp2.json()["workspaces"]]
    assert ws_id in ws_ids


def test_manifest_403_for_non_visible(client: TestClient) -> None:
    uid1, token1 = _reg(client, "mowner@example.com")
    uid2, token2 = _reg(client, "mviewer@example.com")

    resp = client.post("/workspaces", json={"name": "ManifestWS"}, headers={"Authorization": f"Bearer {token1}"})
    ws_id = resp.json()["workspace_id"]
    page_id = _pub(client, token1, ws_id, "private")

    resp2 = client.get(f"/portal/pages/{page_id}/manifest", headers={"Authorization": f"Bearer {token2}"})
    assert resp2.status_code == 403
    assert resp2.json()["detail"]["code"] == "page_not_visible"


def test_manifest_404_for_nonexistent(client: TestClient) -> None:
    uid, token = _reg(client, "manifest404@example.com")
    resp = client.get("/portal/pages/nonexistent-page-id/manifest", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
