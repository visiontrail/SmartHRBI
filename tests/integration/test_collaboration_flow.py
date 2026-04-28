from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _setup_env(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / "state.db"}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "collab-test-secret-key")
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


def _register_and_get_token(client: TestClient, email: str, name: str = "User") -> tuple[str, str]:
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "display_name": name,
        "job_id": 1,
    })
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    return data["user"]["id"], data["access_token"]


def _make_workspace(client: TestClient, token: str, name: str = "Test WS") -> str:
    resp = client.post("/workspaces", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.json()
    return resp.json()["workspace_id"]


def test_search_invite_accept_flow(client: TestClient) -> None:
    owner_id, owner_token = _register_and_get_token(client, "owner@example.com", "Owner")
    member_id, member_token = _register_and_get_token(client, "member@example.com", "Member")
    ws_id = _make_workspace(client, owner_token)

    # owner invites member directly
    add_resp = client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": member_id, "role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert add_resp.status_code == 200

    # member can see workspace
    ws_resp = client.get(f"/workspaces/{ws_id}", headers={"Authorization": f"Bearer {member_token}"})
    assert ws_resp.status_code == 200
    assert ws_resp.json()["role"] == "editor"


def test_invite_link_accept(client: TestClient) -> None:
    owner_id, owner_token = _register_and_get_token(client, "linkownerabc@example.com", "Owner")
    user_id, user_token = _register_and_get_token(client, "linkmemberxyz@example.com", "Member")
    ws_id = _make_workspace(client, owner_token, "LinkWS")

    # create invite
    invite_resp = client.post(
        f"/workspaces/{ws_id}/invites",
        json={"role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert invite_resp.status_code == 200
    invite_url = invite_resp.json()["invite_url"]
    token_part = invite_url.split("/invites/", 1)[1]

    # user accepts invite
    accept_resp = client.post(
        f"/invites/{token_part}/accept",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert accept_resp.status_code == 200
    assert not accept_resp.json()["already_member"]


def test_invite_revoke(client: TestClient) -> None:
    owner_id, owner_token = _register_and_get_token(client, "revokeowner@example.com", "Owner")
    user_id, user_token = _register_and_get_token(client, "revokeuser@example.com", "User")
    ws_id = _make_workspace(client, owner_token, "RevokeWS")

    invite_resp = client.post(
        f"/workspaces/{ws_id}/invites",
        json={"role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    invite_id = invite_resp.json()["id"]
    token_part = invite_resp.json()["invite_url"].split("/invites/", 1)[1]

    # revoke
    revoke_resp = client.delete(
        f"/workspaces/{ws_id}/invites/{invite_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert revoke_resp.status_code == 200

    # accept should fail with 410
    accept_resp = client.post(
        f"/invites/{token_part}/accept",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert accept_resp.status_code == 410
    assert accept_resp.json()["detail"]["code"] == "invite_revoked"


def test_already_member_accepts_again(client: TestClient) -> None:
    owner_id, owner_token = _register_and_get_token(client, "idem_owner@example.com", "Owner")
    user_id, user_token = _register_and_get_token(client, "idem_user@example.com", "User")
    ws_id = _make_workspace(client, owner_token, "IdemWS")

    invite_resp = client.post(
        f"/workspaces/{ws_id}/invites",
        json={"role": "editor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    token_part = invite_resp.json()["invite_url"].split("/invites/", 1)[1]

    client.post(f"/invites/{token_part}/accept", headers={"Authorization": f"Bearer {user_token}"})
    resp2 = client.post(f"/invites/{token_part}/accept", headers={"Authorization": f"Bearer {user_token}"})
    assert resp2.status_code == 200
    assert resp2.json()["already_member"] is True
