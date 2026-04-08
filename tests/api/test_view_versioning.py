from __future__ import annotations

import json
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


def test_view_rollback_restores_history_and_writes_audit_event(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
        first = client.post(
            "/views",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "Versioned",
                "ai_state": {
                    "active_spec": {
                        "engine": "recharts",
                        "chart_type": "bar",
                        "title": "V1",
                        "data": [{"department": "HR", "metric_value": 5}],
                        "config": {"xKey": "department", "yKey": "metric_value"},
                    }
                },
            },
            headers=headers,
        )
        assert first.status_code == 200
        view_id = first.json()["view_id"]

        second = client.post(
            "/views",
            json={
                "view_id": view_id,
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": "dataset_alpha",
                "title": "Versioned",
                "ai_state": {
                    "active_spec": {
                        "engine": "recharts",
                        "chart_type": "line",
                        "title": "V2",
                        "data": [{"month": "2026-01", "metric_value": 7}],
                        "config": {"xKey": "month", "yKey": "metric_value"},
                    }
                },
            },
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["version"] == 2

        rollback = client.post(
            f"/views/{view_id}/rollback/1",
            json={
                "user_id": "alice",
                "project_id": "north",
                "role": "viewer",
                "department": "HR",
                "clearance": 1,
            },
            headers=headers,
        )
        assert rollback.status_code == 200
        rollback_payload = rollback.json()
        assert rollback_payload["rolled_back_to"] == 1
        assert rollback_payload["version"] == 3

        fetched = client.get(f"/views/{view_id}", headers=headers)
        assert fetched.status_code == 200
        fetched_payload = fetched.json()
        assert fetched_payload["current_version"] == 3
        assert fetched_payload["ai_state"]["active_spec"]["title"] == "V1"
        assert [item["version"] for item in fetched_payload["versions"]] == [1, 2, 3]

    audit_log = tmp_path / "view_events.log"
    assert audit_log.exists()
    events = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    rollback_events = [item for item in events if item.get("event") == "rollback" and item.get("view_id") == view_id]
    assert rollback_events
    assert rollback_events[-1]["target_version"] == 1
