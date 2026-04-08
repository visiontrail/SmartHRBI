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


def test_quality_report_tracks_file_and_column_level_findings(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)
    numeric_salary = _excel_bytes(
        [
            {"Employee ID": "E-001", "Salary": 1000, "Department": "HR"},
            {"Employee ID": "E-002", "Salary": 1100, "Department": "HR"},
        ]
    )
    string_salary = _excel_bytes(
        [
            {"Employee ID": "E-003", "Salary": "unknown", "Department": None},
        ]
    )

    with TestClient(app) as client:
        headers = auth_headers(client, user_id="quality-user", project_id="project-1")
        upload = client.post(
            "/datasets/upload",
            data={"user_id": "quality-user", "project_id": "project-1"},
            headers=headers,
            files=[
                (
                    "files",
                    (
                        "numeric.xlsx",
                        numeric_salary,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
                (
                    "files",
                    (
                        "string.xlsx",
                        string_salary,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
            ],
        )
        assert upload.status_code == 200
        batch_id = upload.json()["batch_id"]

        response = client.get(f"/datasets/{batch_id}/quality-report", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["batch_id"] == batch_id
    assert {item["file_name"] for item in payload["files"]} == {"numeric.xlsx", "string.xlsx"}

    salary_entry = next(item for item in payload["columns"] if item["column"] == "salary")
    assert salary_entry["type_drift"] is True
    assert set(salary_entry["types_by_file"].values()) == {"number", "string"}

    assert any(issue["rule"] == "type_drift" and issue["column"] == "salary" for issue in payload["blocking_issues"])
    assert payload["can_publish_to_semantic_layer"] is False
