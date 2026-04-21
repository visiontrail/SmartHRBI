from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.agentic_ingestion.feature_flags import ensure_agentic_ingestion_enabled
from apps.api.agentic_ingestion.router import router as ingestion_router
from apps.api.config import get_settings


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("AGENTIC_INGESTION_ENABLED", "false")
    get_settings.cache_clear()


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(ingestion_router)
    return TestClient(app)


def test_ingestion_healthz_ignores_disabled_flag(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with _build_test_client() as client:
        response = client.get("/ingestion/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["stage"] == "M6"


def test_ingestion_healthz_respects_agentic_flag(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENTIC_INGESTION_ENABLED", "true")
    get_settings.cache_clear()

    with _build_test_client() as client:
        response = client.get("/ingestion/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["stage"] == "M6"


@pytest.mark.parametrize("enabled", [False, True])
def test_agentic_flag_guard_is_compatibility_noop(enabled: bool) -> None:
    ensure_agentic_ingestion_enabled(enabled)
