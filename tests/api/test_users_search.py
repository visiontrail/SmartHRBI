from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _setup_env(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / "state.db"}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret-for-search-tests")
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
def client_with_user(monkeypatch: Any, tmp_path: Path):
    _setup_env(monkeypatch, tmp_path)

    from apps.api.config import get_settings
    from apps.api.workspaces import clear_workspace_service_cache
    from apps.api.published_pages import clear_published_page_store_cache

    get_settings.cache_clear()
    clear_workspace_service_cache()
    clear_published_page_store_cache()

    from apps.api.db_migrations import apply_migrations
    apply_migrations()

    from apps.api.main import app
    c = TestClient(app, raise_server_exceptions=True)

    reg = c.post("/auth/register", json={
        "email": "searcher@example.com",
        "password": "password123",
        "display_name": "Searcher",
        "job_id": 1,
    })
    c.post("/auth/register", json={
        "email": "li.lei@example.com",
        "password": "password123",
        "display_name": "李雷",
        "job_id": 2,
    })
    token = reg.json()["access_token"]
    return c, token


def test_search_too_short(client_with_user) -> None:
    c, token = client_with_user
    resp = c.get("/users/search?q=a", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "query_too_short"


def test_search_returns_results(client_with_user) -> None:
    c, token = client_with_user
    resp = c.get("/users/search?q=li", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    result = data["users"][0]
    assert "email_masked" in result
    assert "***" in result["email_masked"]


def test_search_requires_auth(client_with_user) -> None:
    c, _ = client_with_user
    from apps.api.main import app
    from fastapi.testclient import TestClient as _TC
    fresh = _TC(app, raise_server_exceptions=True, cookies={})
    resp = fresh.get("/users/search?q=li")
    assert resp.status_code == 401
