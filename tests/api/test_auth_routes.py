from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _setup_env(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'state.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret-for-auth-tests")
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


def test_register_success(client: TestClient) -> None:
    payload = {
        "email": "test@example.com",
        "password": "password123",
        "display_name": "Test User",
        "job_id": 1,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@example.com"


def test_register_duplicate_email(client: TestClient) -> None:
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "display_name": "User",
        "job_id": 1,
    }
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/register", json={"email": "DUP@example.com", **payload})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "email_taken"


def test_register_password_too_short(client: TestClient) -> None:
    payload = {
        "email": "short@example.com",
        "password": "abc",
        "display_name": "User",
        "job_id": 1,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422


def test_register_invalid_job_id(client: TestClient) -> None:
    payload = {
        "email": "badjob@example.com",
        "password": "password123",
        "display_name": "User",
        "job_id": 9999,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "invalid_job_id"


def test_email_login_success(client: TestClient) -> None:
    client.post("/auth/register", json={
        "email": "login@example.com",
        "password": "mypassword",
        "display_name": "Login User",
        "job_id": 1,
    })
    resp = client.post("/auth/email-login", json={
        "email": "login@example.com",
        "password": "mypassword",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_email_login_wrong_password(client: TestClient) -> None:
    client.post("/auth/register", json={
        "email": "fail@example.com",
        "password": "correctpassword",
        "display_name": "Fail User",
        "job_id": 1,
    })
    resp = client.post("/auth/email-login", json={
        "email": "fail@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


def test_email_login_nonexistent_user(client: TestClient) -> None:
    resp = client.post("/auth/email-login", json={
        "email": "nobody@example.com",
        "password": "anypassword",
    })
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


def test_auth_me(client: TestClient) -> None:
    reg = client.post("/auth/register", json={
        "email": "me@example.com",
        "password": "mypassword1",
        "display_name": "Me User",
        "job_id": 1,
    })
    token = reg.json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "me@example.com"
    assert "available_workspaces" in data


def test_logout(client: TestClient) -> None:
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
