from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.chat import clear_chat_stream_service_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from tests.auth_utils import auth_headers


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'views.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_chat_stream_service_cache()
    clear_view_storage_service_cache()


def test_save_view_requires_authenticated_user(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/views",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "unauthorized",
                "ai_state": {"active_spec": {"chart_type": "bar"}},
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_save_view_returns_share_link_openable_in_new_session(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north", role="admin", clearance=9)
        create = client.post(
            "/views",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "Shareable",
                "ai_state": {
                    "active_spec": {
                        "engine": "recharts",
                        "chart_type": "line",
                        "title": "Trend",
                        "data": [{"month": "2026-01", "metric_value": 3}],
                        "config": {"xKey": "month", "yKey": "metric_value"},
                    }
                },
            },
            headers=headers,
        )
        assert create.status_code == 200
        payload = create.json()
        assert payload["share_url"] == f"/share/{payload['view_id']}"

    with TestClient(app) as another_session:
        headers = auth_headers(
            another_session,
            user_id="another-user",
            project_id="north",
            role="viewer",
            clearance=1,
        )
        shared = another_session.get(payload["share_url"], headers=headers)

    assert shared.status_code == 200
    shared_payload = shared.json()
    assert shared_payload["view_id"] == payload["view_id"]
    assert shared_payload["ai_state"]["active_spec"]["chart_type"] == "line"
