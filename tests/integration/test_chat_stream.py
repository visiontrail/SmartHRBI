from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path

import pandas as pd
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
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
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


def _excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def _upload_dataset(client: TestClient) -> str:
    upload_file = _excel_bytes(
        [
            {"employee id": "E-001", "department": "HR", "status": "active", "salary": 1000},
            {"employee id": "E-002", "department": "HR", "status": "inactive", "salary": 1200},
            {"employee id": "E-003", "department": "PM", "status": "active", "salary": 900},
        ]
    )

    headers = auth_headers(client, user_id="alice", project_id="north", role="admin")
    response = client.post(
        "/datasets/upload",
        data={"user_id": "alice", "project_id": "north"},
        headers=headers,
        files=[
            (
                "files",
                (
                    "employees.xlsx",
                    upload_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )
    assert response.status_code == 200
    return response.json()["dataset_table"]


def _read_sse_events(response) -> tuple[list[dict[str, object]], float | None]:
    events: list[dict[str, object]] = []
    current: dict[str, object] = {}
    first_chunk_at: float | None = None

    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if line and first_chunk_at is None:
            first_chunk_at = time.perf_counter()

        if line == "":
            if {"id", "event", "data"}.issubset(current):
                payload = json.loads(str(current["data"]))
                events.append(
                    {
                        "id": int(current["id"]),
                        "event": str(current["event"]),
                        "data": payload,
                    }
                )
            current = {}
            continue

        if line.startswith("id:"):
            current["id"] = line.split(":", 1)[1].strip()
            continue
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            current["data"] = line.split(":", 1)[1].strip()

    return events, first_chunk_at


def test_chat_stream_emits_required_events_with_low_first_token_latency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )
        start = time.perf_counter()
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "conv-stream-1",
                "request_id": "chat-req-1",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "role": "viewer",
                "department": "HR",
                "clearance": 1,
                "message": "按部门看在职人数",
            },
            headers=headers,
        ) as response:
            assert response.status_code == 200
            events, first_chunk_at = _read_sse_events(response)

    assert first_chunk_at is not None
    assert first_chunk_at - start < 2.0
    assert [item["event"] for item in events] == ["reasoning", "tool", "spec", "final"]
    spec_event = events[2]["data"]
    assert spec_event["spec"]["engine"] in {"recharts", "echarts"}


def test_chat_stream_reconnect_replays_missing_events(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = _upload_dataset(client)
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )

        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "conv-stream-2",
                "request_id": "chat-req-2",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "role": "viewer",
                "department": "HR",
                "clearance": 1,
                "message": "按部门看在职人数",
            },
            headers=headers,
        ) as first_response:
            assert first_response.status_code == 200
            first_events, _ = _read_sse_events(first_response)

        assert len(first_events) == 4
        assert [item["id"] for item in first_events] == [1, 2, 3, 4]

        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "conversation_id": "conv-stream-2",
                "request_id": "chat-req-2-replay",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "last_event_id": 2,
                "message": None,
            },
            headers=headers,
        ) as replay_response:
            assert replay_response.status_code == 200
            replay_events, _ = _read_sse_events(replay_response)

    assert [item["id"] for item in replay_events] == [3, 4]
    assert [item["event"] for item in replay_events] == ["spec", "final"]
    assert replay_events[-1]["data"]["status"] in {"completed", "failed"}
