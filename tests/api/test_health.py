from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app, configure_application_logging


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))


def test_healthz_success(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "SmartHRBI API"
    assert payload["environment"] == "development"
    assert (tmp_path / "uploads").exists()


def test_configure_application_logging_binds_smarthrbi_logger_to_uvicorn_handler() -> None:
    app_logger = logging.getLogger("smarthrbi")
    uvicorn_logger = logging.getLogger("uvicorn.error")
    original_app_handlers = list(app_logger.handlers)
    original_app_level = app_logger.level
    original_app_propagate = app_logger.propagate
    original_uvicorn_handlers = list(uvicorn_logger.handlers)

    handler = logging.StreamHandler()
    uvicorn_logger.handlers = [handler]

    try:
        configure_application_logging("INFO")
        assert app_logger.level == logging.INFO
        assert app_logger.handlers == [handler]
        assert app_logger.propagate is False
    finally:
        app_logger.handlers = original_app_handlers
        app_logger.setLevel(original_app_level)
        app_logger.propagate = original_app_propagate
        uvicorn_logger.handlers = original_uvicorn_handlers
