from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from tests.auth_utils import auth_headers


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_dataset_service_cache()


def test_legacy_upload_quality_report_route_is_removed(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="quality-user", project_id="project-1")
        response = client.get("/datasets/batch-demo/quality-report", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
