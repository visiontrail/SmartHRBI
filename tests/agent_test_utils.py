from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from apps.api.agent_runtime import clear_agent_runtime_cache
from apps.api.audit import clear_audit_logger_cache
from apps.api.auth import clear_auth_cache
from apps.api.chat import clear_chat_stream_service_cache
from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.semantic import clear_semantic_cache
from apps.api.tool_calling import clear_tool_calling_service_cache
from apps.api.views import clear_view_storage_service_cache
from tests.auth_utils import auth_headers


def set_agent_env(
    monkeypatch,
    tmp_path: Path,
    *,
    chat_engine: str = "agent_primary",
    chat_engine_users: str = "",
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'views.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CHAT_ENGINE", chat_engine)
    monkeypatch.setenv("CHAT_ENGINE_USERS", chat_engine_users)
    monkeypatch.setenv("CLAUDE_AGENT_SDK_ENABLED", "true")
    monkeypatch.setenv("AGENT_MAX_TOOL_STEPS", "6")
    monkeypatch.setenv("AGENT_MAX_SQL_ROWS", "200")
    monkeypatch.setenv("AGENT_MAX_SQL_SCAN_ROWS", "10000")
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "25")

    get_settings.cache_clear()
    clear_auth_cache()
    clear_audit_logger_cache()
    clear_dataset_service_cache()
    clear_semantic_cache()
    clear_tool_calling_service_cache()
    clear_chat_stream_service_cache()
    clear_view_storage_service_cache()
    clear_agent_runtime_cache()


def excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def upload_dataset(
    client: TestClient,
    *,
    rows: list[dict[str, object]],
    user_id: str = "alice",
    project_id: str = "north",
    role: str = "admin",
    department: str | None = "HR",
    clearance: int = 9,
    filename: str = "dataset.xlsx",
) -> str:
    headers = auth_headers(
        client,
        user_id=user_id,
        project_id=project_id,
        role=role,
        department=department,
        clearance=clearance,
    )
    response = client.post(
        "/datasets/upload",
        data={"user_id": user_id, "project_id": project_id},
        headers=headers,
        files=[
            (
                "files",
                (
                    filename,
                    excel_bytes(rows),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )
    assert response.status_code == 200, response.text
    return str(response.json()["dataset_table"])


def read_sse_events(response) -> tuple[list[dict[str, Any]], float | None]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
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
