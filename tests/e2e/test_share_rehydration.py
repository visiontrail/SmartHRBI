from __future__ import annotations

import time
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


def test_share_rehydration_restores_saved_ui_without_llm(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as creator:
        creator_headers = auth_headers(creator, user_id="alice", project_id="north", role="admin", clearance=9)
        create = creator.post(
            "/views",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "Rehydrate Demo",
                "ai_state": {
                    "conversation_id": "conv-1",
                    "messages": [
                        {"id": "m-1", "role": "user", "text": "show attrition trend"},
                        {"id": "m-2", "role": "assistant", "text": "done"},
                    ],
                    "active_spec": {
                        "engine": "recharts",
                        "chart_type": "line",
                        "title": "Attrition Trend",
                        "data": [
                            {"month": "2026-01", "metric_value": 0.1},
                            {"month": "2026-02", "metric_value": 0.09},
                        ],
                        "config": {"xKey": "month", "yKey": "metric_value"},
                    },
                },
            },
            headers=creator_headers,
        )
        assert create.status_code == 200
        share_url = create.json()["share_url"]

    with TestClient(app) as consumer:
        consumer_headers = auth_headers(
            consumer,
            user_id="consumer",
            project_id="north",
            role="viewer",
            clearance=1,
        )
        started = time.perf_counter()
        shared = consumer.get(share_url, headers=consumer_headers)
        elapsed = time.perf_counter() - started

    assert shared.status_code == 200
    assert elapsed < 1.5

    payload = shared.json()
    assert payload["ai_state"]["active_spec"]["title"] == "Attrition Trend"
    assert payload["ai_state"]["messages"][0]["text"] == "show attrition trend"
