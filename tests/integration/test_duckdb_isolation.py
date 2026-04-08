from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache, get_dataset_service
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


def _excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def _upload(client: TestClient, *, user_id: str, project_id: str, rows: list[dict[str, object]]) -> dict:
    headers = auth_headers(client, user_id=user_id, project_id=project_id, role="admin")
    response = client.post(
        "/datasets/upload",
        data={"user_id": user_id, "project_id": project_id},
        headers=headers,
        files=[
            (
                "files",
                (
                    f"{user_id}.xlsx",
                    _excel_bytes(rows),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
    )
    assert response.status_code == 200
    return response.json()


def test_duckdb_session_isolation_between_users(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        upload_a = _upload(
            client,
            user_id="user-a",
            project_id="project-1",
            rows=[
                {"Employee ID": "A-1", "Department": "HR"},
                {"Employee ID": "A-2", "Department": "HR"},
            ],
        )
        upload_b = _upload(
            client,
            user_id="user-b",
            project_id="project-1",
            rows=[
                {"Employee ID": "B-1", "Department": "PM"},
            ],
        )

    settings = get_settings()
    service = get_dataset_service(settings.upload_dir)

    tables_a = service.list_tables(user_id="user-a", project_id="project-1")
    tables_b = service.list_tables(user_id="user-b", project_id="project-1")

    assert upload_a["dataset_table"] in tables_a
    assert upload_b["dataset_table"] in tables_b
    assert upload_a["dataset_table"] not in tables_b
    assert upload_b["dataset_table"] not in tables_a

    assert (
        service.get_row_count(
            user_id="user-a",
            project_id="project-1",
            table_name=upload_a["dataset_table"],
        )
        == 2
    )
    assert (
        service.get_row_count(
            user_id="user-b",
            project_id="project-1",
            table_name=upload_b["dataset_table"],
        )
        == 1
    )
