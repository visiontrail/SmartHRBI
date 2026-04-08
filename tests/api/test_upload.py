from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
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


def _excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def test_upload_supports_multiple_excel_files(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)
    file_one = _excel_bytes(
        [
            {"Employee ID": "E-001", "Department": "HR", "Salary": 1000},
            {"Employee ID": "E-002", "Department": "PM", "Salary": 1200},
        ]
    )
    file_two = _excel_bytes(
        [
            {"salary": 1500, "dept": "HR", "employee id": "E-003"},
        ]
    )

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north")
        response = client.post(
            "/datasets/upload",
            data={"user_id": "alice", "project_id": "north"},
            headers=headers,
            files=[
                (
                    "files",
                    (
                        "employees-a.xlsx",
                        file_one,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
                (
                    "files",
                    (
                        "employees-b.xlsx",
                        file_two,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
            ],
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_count"] == 2
    assert payload["batch_id"]
    assert payload["session_id"].startswith("alice__north__")
    assert payload["dataset_table"].startswith("dataset_")


def test_upload_rejects_non_excel_file(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north")
        response = client.post(
            "/datasets/upload",
            data={"user_id": "alice", "project_id": "north"},
            headers=headers,
            files=[
                (
                    "files",
                    ("notes.txt", b"not-an-excel", "text/plain"),
                ),
            ],
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "allowed=.xlsx" in detail["reasons"][1]


def test_upload_accepts_ten_files_in_one_batch(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)
    tiny_excel = _excel_bytes([{"Employee ID": "E-001", "Department": "HR"}])

    files = [
        (
            "files",
            (
                f"employees-{index}.xlsx",
                tiny_excel,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
        for index in range(10)
    ]

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="alice", project_id="north")
        response = client.post(
            "/datasets/upload",
            data={"user_id": "alice", "project_id": "north"},
            headers=headers,
            files=files,
        )

    assert response.status_code == 200
    assert response.json()["file_count"] == 10
