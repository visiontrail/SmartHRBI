from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.audit import clear_audit_logger_cache
from apps.api.auth import clear_auth_cache, get_token_service
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from tests.auth_utils import expect_error_code


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


def test_core_api_requires_bearer_token(monkeypatch, tmp_path: Path, caplog) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with caplog.at_level(logging.WARNING, logger="cognitrix.auth"):
        with TestClient(app) as client:
            response = client.get("/semantic/metrics")

    assert "reason=missing_token" in caplog.text
    expect_error_code(response, "AUTH_REQUIRED", status_code=401)


def test_expired_token_returns_token_expired(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    expired_token, _ = get_token_service().issue_token(
        user_id="alice",
        project_id="north",
        role="viewer",
        department="HR",
        clearance=1,
        expires_in=-1,
    )

    with TestClient(app) as client:
        response = client.get(
            "/semantic/metrics",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

    expect_error_code(response, "TOKEN_EXPIRED", status_code=401)
