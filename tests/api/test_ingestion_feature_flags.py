from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from apps.api.agentic_ingestion.feature_flags import (
    ensure_agentic_ingestion_enabled,
    ensure_legacy_dataset_upload_enabled,
)
from apps.api.agentic_ingestion.router import router as ingestion_router
from apps.api.config import get_settings


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(ingestion_router)
    return TestClient(app)


def test_ingestion_healthz_disabled_by_default(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with _build_test_client() as client:
        response = client.get("/ingestion/healthz")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "AGENTIC_INGESTION_DISABLED"


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


@pytest.mark.parametrize(
    ("enabled", "expected_code"),
    [
        (False, "AGENTIC_INGESTION_DISABLED"),
        (True, None),
    ],
)
def test_agentic_flag_guard(enabled: bool, expected_code: str | None) -> None:
    if expected_code is None:
        ensure_agentic_ingestion_enabled(enabled)
        return

    with pytest.raises(HTTPException) as exc_info:
        ensure_agentic_ingestion_enabled(enabled)

    assert exc_info.value.detail["code"] == expected_code


def test_legacy_upload_flag_guard() -> None:
    ensure_legacy_dataset_upload_enabled(True)

    with pytest.raises(HTTPException) as exc_info:
        ensure_legacy_dataset_upload_enabled(False)

    assert exc_info.value.detail["code"] == "LEGACY_UPLOAD_DISABLED"
