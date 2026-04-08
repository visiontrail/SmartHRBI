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


def test_state_storage_supports_version_increment_and_latency_target(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
        first = client.post(
            "/views",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "Attrition Snapshot",
                "ai_state": {
                    "active_spec": {
                        "engine": "recharts",
                        "chart_type": "bar",
                        "title": "Headcount",
                        "data": [{"department": "HR", "metric_value": 10}],
                        "config": {"xKey": "department", "yKey": "metric_value"},
                    },
                    "messages": [{"id": "m-1", "role": "assistant", "text": "done"}],
                },
            },
            headers=headers,
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["version"] == 1
        assert first_payload["duration_ms"] <= 200

        second = client.post(
            "/views",
            json={
                "view_id": first_payload["view_id"],
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "Attrition Snapshot v2",
                "ai_state": {
                    "active_spec": {
                        "engine": "recharts",
                        "chart_type": "single_value",
                        "title": "Active Employees",
                        "data": [{"metric_value": 18}],
                        "config": {"yKey": "metric_value"},
                    },
                },
            },
            headers=headers,
        )
        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["version"] == 2

        fetched = client.get(f"/views/{first_payload['view_id']}", headers=headers)
        assert fetched.status_code == 200
        fetched_payload = fetched.json()
        assert fetched_payload["current_version"] == 2
        assert fetched_payload["ai_state"]["active_spec"]["chart_type"] == "single_value"
        assert [item["version"] for item in fetched_payload["versions"]] == [1, 2]
