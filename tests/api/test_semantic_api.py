from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache
from apps.api.main import app
from apps.api.semantic import clear_semantic_cache
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


def _excel_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)
    return buffer.getvalue()


def test_semantic_metrics_api_lists_metrics(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )
        response = client.get("/semantic/metrics", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 15
    names = {item["name"] for item in payload["metrics"]}
    assert "attrition_rate" in names


def test_semantic_query_api_executes_metric_and_applies_security(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    upload_file = _excel_bytes(
        [
            {"employee id": "E-001", "department": "HR", "status": "active", "salary": 1000},
            {"employee id": "E-002", "department": "HR", "status": "inactive", "salary": 1100},
            {"employee id": "E-003", "department": "PM", "status": "active", "salary": 1200},
        ]
    )

    with TestClient(app) as client:
        upload_headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="admin",
            department="HR",
            clearance=9,
        )
        query_headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="viewer",
            department="HR",
            clearance=1,
        )
        upload = client.post(
            "/datasets/upload",
            data={"user_id": "alice", "project_id": "north"},
            headers=upload_headers,
            files=[
                (
                    "files",
                    (
                        "employees.xlsx",
                        upload_file,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                ),
            ],
        )

        assert upload.status_code == 200
        dataset_table = upload.json()["dataset_table"]

        query_response = client.post(
            "/semantic/query",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "metric": "active_employee_count",
                "group_by": ["department"],
                "role": "viewer",
                "department": "HR",
                "clearance": 1,
            },
            headers=query_headers,
        )

        assert query_response.status_code == 200
        payload = query_response.json()
        assert payload["metric"] == "active_employee_count"
        assert payload["row_count"] == 1
        assert payload["rows"] == [{"department": "HR", "metric_value": 1}]

        forbidden_response = client.post(
            "/semantic/query",
            json={
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "metric": "avg_salary",
                "role": "viewer",
                "department": "HR",
                "clearance": 1,
            },
            headers=query_headers,
        )

    assert forbidden_response.status_code == 403
    detail = forbidden_response.json()["detail"]
    assert detail["code"] == "ACCESS_DENIED"
    assert "salary" not in detail["message"].lower()
