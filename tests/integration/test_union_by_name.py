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


def test_union_by_name_aligns_columns_and_fills_null(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    file_a = _excel_bytes(
        [
            {"Employee ID": "E-001", "Department": "HR", "Salary": 1000},
            {"Employee ID": "E-002", "Department": "PM", "Salary": 1100},
        ]
    )
    file_b = _excel_bytes(
        [
            {"salary": 1500, "dept": "HR", "employee id": "E-003", "Nickname": "Ace"},
        ]
    )

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="union-user", project_id="project-1", role="admin")
        response = client.post(
            "/datasets/upload",
            data={"user_id": "union-user", "project_id": "project-1"},
            headers=headers,
            files=[
                (
                    "files",
                    ("a.xlsx", file_a, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ),
                (
                    "files",
                    ("b.xlsx", file_b, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ),
            ],
        )

    assert response.status_code == 200
    payload = response.json()

    unrecognized = payload["diagnostics"]["unrecognized_columns"]
    assert unrecognized == [{"file_name": "b.xlsx", "columns": ["nickname"]}]

    service = get_dataset_service(get_settings().upload_dir)
    table_name = payload["dataset_table"]
    with service.session_manager.connection("union-user", "project-1") as conn:
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()]
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        null_count = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM "{table_name}"
            WHERE source_file = 'a.xlsx' AND nickname IS NULL
            """
        ).fetchone()[0]

    assert {"employee_id", "department", "salary", "nickname", "source_file"}.issubset(set(columns))
    assert row_count == 3
    assert null_count == 2
