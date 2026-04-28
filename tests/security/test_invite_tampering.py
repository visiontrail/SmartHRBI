from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _setup_env(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / "state.db"}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "tamper-test-secret-key-123")
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


def _register(client: TestClient, email: str) -> tuple[str, str]:
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": "User",
        "job_id": 1,
    })
    assert resp.status_code == 200
    d = resp.json()
    return d["user"]["id"], d["access_token"]


def test_tampered_token_rejected(client: TestClient) -> None:
    owner_id, owner_token = _register(client, "tamper_owner@example.com")
    user_id, user_token = _register(client, "tamper_user@example.com")

    resp = client.post(
        "/workspaces",
        json={"name": "TamperWS"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    ws_id = resp.json()["workspace_id"]

    invite_resp = client.post(
        f"/workspaces/{ws_id}/invites",
        json={"role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    invite_url = invite_resp.json()["invite_url"]
    raw_token = invite_url.split("/invites/", 1)[1]

    # tamper with the token
    parts = raw_token.split(".")
    if len(parts) >= 2:
        tampered = raw_token[:-5] + "XXXXX"
    else:
        tampered = raw_token + "tampered"

    accept_resp = client.post(
        f"/invites/{tampered}/accept",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert accept_resp.status_code in (400, 410)


def test_nonexistent_token_rejected(client: TestClient) -> None:
    _, user_token = _register(client, "ghost_user@example.com")
    resp = client.post(
        "/invites/totally-fake-token-that-does-not-exist/accept",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code in (400, 410)


def test_max_uses_enforced(client: TestClient) -> None:
    owner_id, owner_token = _register(client, "maxuse_owner@example.com")
    user1_id, user1_token = _register(client, "maxuse_user1@example.com")
    user2_id, user2_token = _register(client, "maxuse_user2@example.com")

    resp = client.post(
        "/workspaces",
        json={"name": "MaxUseWS"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    ws_id = resp.json()["workspace_id"]

    invite_resp = client.post(
        f"/workspaces/{ws_id}/invites",
        json={"role": "editor", "max_uses": 1},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    raw_token = invite_resp.json()["invite_url"].split("/invites/", 1)[1]

    r1 = client.post(f"/invites/{raw_token}/accept", headers={"Authorization": f"Bearer {user1_token}"})
    assert r1.status_code == 200

    r2 = client.post(f"/invites/{raw_token}/accept", headers={"Authorization": f"Bearer {user2_token}"})
    assert r2.status_code == 410
    assert r2.json()["detail"]["code"] == "invite_exhausted"
