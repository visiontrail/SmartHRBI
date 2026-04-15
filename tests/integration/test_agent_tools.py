from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app
from tests.agent_test_utils import set_agent_env, upload_dataset
from tests.auth_utils import auth_headers


def test_agent_tools_expose_schema_sample_semantic_and_readonly_sql(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR", "status": "active", "hire_year": 2022},
                {"employee_id": "E-002", "department": "HR", "status": "inactive", "hire_year": 2023},
                {"employee_id": "E-003", "department": "PM", "status": "active", "hire_year": 2023},
            ],
        )
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="admin",
            department="HR",
            clearance=9,
        )

        list_tables = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-conv",
                "request_id": "agent-tools-list",
                "idempotency_key": "agent-tools-list",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {"name": "list_tables", "arguments": {}},
            },
            headers=headers,
        )
        describe = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-conv",
                "request_id": "agent-tools-describe",
                "idempotency_key": "agent-tools-describe",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {"name": "describe_table", "arguments": {"table": dataset_table, "sample_limit": 3}},
            },
            headers=headers,
        )
        metric_catalog = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-conv",
                "request_id": "agent-tools-metrics",
                "idempotency_key": "agent-tools-metrics",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {"name": "get_metric_catalog", "arguments": {}},
            },
            headers=headers,
        )
        semantic = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-conv",
                "request_id": "agent-tools-semantic",
                "idempotency_key": "agent-tools-semantic",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {"name": "run_semantic_query", "arguments": {"metric": "active_employee_count", "group_by": ["department"]}},
            },
            headers=headers,
        )
        readonly_sql = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-conv",
                "request_id": "agent-tools-sql",
                "idempotency_key": "agent-tools-sql",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {
                    "name": "execute_readonly_sql",
                    "arguments": {
                        "sql": f'SELECT "hire_year", COUNT(*) AS metric_value FROM "{dataset_table}" GROUP BY 1 ORDER BY 1',
                        "max_rows": 20,
                    },
                },
            },
            headers=headers,
        )
        distinct = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-conv",
                "request_id": "agent-tools-distinct",
                "idempotency_key": "agent-tools-distinct",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": dataset_table,
                "tool": {"name": "get_distinct_values", "arguments": {"field": "department", "limit": 10}},
            },
            headers=headers,
        )

    assert list_tables.status_code == 200
    assert list_tables.json()["result"]["active_dataset_table"] == dataset_table
    assert dataset_table in list_tables.json()["result"]["tables"]

    assert describe.status_code == 200
    describe_payload = describe.json()["result"]
    assert describe_payload["table"] == dataset_table
    assert any(column["name"] == "hire_year" for column in describe_payload["columns"])
    assert describe_payload["sample_rows"]

    assert metric_catalog.status_code == 200
    assert metric_catalog.json()["result"]["count"] >= 1

    assert semantic.status_code == 200
    assert semantic.json()["result"]["metric"] == "active_employee_count"

    assert readonly_sql.status_code == 200
    sql_rows = readonly_sql.json()["result"]["rows"]
    assert sql_rows == [{"hire_year": 2022, "metric_value": 1}, {"hire_year": 2023, "metric_value": 2}]

    assert distinct.status_code == 200
    distinct_values = distinct.json()["result"]["values"]
    assert distinct_values[0]["value"] == "HR"


def test_agent_tools_fallback_to_existing_table_when_request_dataset_table_mismatches(
    monkeypatch, tmp_path: Path
) -> None:
    set_agent_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        uploaded_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-101", "department": "HR", "status": "active"},
                {"employee_id": "E-102", "department": "PM", "status": "active"},
            ],
        )
        headers = auth_headers(
            client,
            user_id="alice",
            project_id="north",
            role="admin",
            department="HR",
            clearance=9,
        )
        stale_dataset_table = "employees_wide"

        list_tables = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-fallback-conv",
                "request_id": "agent-tools-fallback-list",
                "idempotency_key": "agent-tools-fallback-list",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": stale_dataset_table,
                "tool": {"name": "list_tables", "arguments": {}},
            },
            headers=headers,
        )
        describe = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-fallback-conv",
                "request_id": "agent-tools-fallback-describe",
                "idempotency_key": "agent-tools-fallback-describe",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": stale_dataset_table,
                "tool": {"name": "describe_table", "arguments": {"table": stale_dataset_table}},
            },
            headers=headers,
        )
        semantic = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-fallback-conv",
                "request_id": "agent-tools-fallback-semantic",
                "idempotency_key": "agent-tools-fallback-semantic",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": stale_dataset_table,
                "tool": {"name": "run_semantic_query", "arguments": {"metric": "active_employee_count", "group_by": ["department"]}},
            },
            headers=headers,
        )
        readonly_sql = client.post(
            "/chat/tool-call",
            json={
                "conversation_id": "agent-tools-fallback-conv",
                "request_id": "agent-tools-fallback-sql",
                "idempotency_key": "agent-tools-fallback-sql",
                "user_id": "alice",
                "project_id": "north",
                "dataset_table": stale_dataset_table,
                "tool": {
                    "name": "execute_readonly_sql",
                    "arguments": {
                        "sql": f'SELECT "department", COUNT(*) AS metric_value FROM "{uploaded_table}" GROUP BY 1 ORDER BY 1',
                    },
                },
            },
            headers=headers,
        )

    assert list_tables.status_code == 200
    assert list_tables.json()["status"] == "success"
    assert list_tables.json()["result"]["active_dataset_table"] == uploaded_table

    assert describe.status_code == 200
    describe_payload = describe.json()
    assert describe_payload["status"] == "success"
    assert describe_payload["result"]["table"] == uploaded_table

    assert semantic.status_code == 200
    semantic_payload = semantic.json()
    assert semantic_payload["status"] == "success"
    assert sorted(semantic_payload["result"]["rows"], key=lambda row: row["department"]) == [
        {"department": "HR", "metric_value": 1},
        {"department": "PM", "metric_value": 1},
    ]

    assert readonly_sql.status_code == 200
    sql_payload = readonly_sql.json()
    assert sql_payload["status"] == "success"
    assert sql_payload["result"]["rows"] == [{"department": "HR", "metric_value": 1}, {"department": "PM", "metric_value": 1}]
