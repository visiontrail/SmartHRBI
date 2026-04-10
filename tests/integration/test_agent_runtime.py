from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.agent_runtime import AgentRequest, clear_agent_runtime_cache, get_agent_runtime
from apps.api.main import app
from tests.agent_test_utils import set_agent_env, upload_dataset


def test_agent_runtime_supports_single_turn_follow_up_and_restart_recovery(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-001", "department": "HR", "hire_year": 2022},
                {"employee_id": "E-002", "department": "HR", "hire_year": 2023},
                {"employee_id": "E-003", "department": "PM", "hire_year": 2023},
            ],
        )

        runtime = get_agent_runtime()
        first = runtime.run_turn(
            AgentRequest(
                conversation_id="agent-runtime-conv-1",
                request_id="agent-runtime-req-1",
                user_id="alice",
                project_id="north",
                dataset_table=dataset_table,
                message="柱状图显示入职年份统计",
                role="viewer",
                department="HR",
                clearance=1,
            )
        )

        follow_up = runtime.run_turn(
            AgentRequest(
                conversation_id="agent-runtime-conv-1",
                request_id="agent-runtime-req-2",
                user_id="alice",
                project_id="north",
                dataset_table=dataset_table,
                message="改成折线图",
                role="viewer",
                department="HR",
                clearance=1,
            )
        )

    assert first.final_status == "completed"
    assert first.agent_session_id
    assert any(event[0] == "tool_use" for event in first.events)
    assert first.spec["chart_type"] == "bar"
    assert first.ai_state["turn_count"] == 1

    assert follow_up.agent_session_id == first.agent_session_id
    assert follow_up.spec["chart_type"] == "line"
    assert "沿用上一轮查询结果" in follow_up.final_text

    clear_agent_runtime_cache()
    recovered_runtime = get_agent_runtime()
    recovered = recovered_runtime.run_turn(
        AgentRequest(
            conversation_id="agent-runtime-conv-1",
            request_id="agent-runtime-req-3",
            user_id="alice",
            project_id="north",
            dataset_table=dataset_table,
            message="再改成柱状图",
            role="viewer",
            department="HR",
            clearance=1,
        )
    )

    assert recovered.agent_session_id == first.agent_session_id
    assert recovered.spec["chart_type"] == "bar"
    assert recovered_runtime.get_persisted_session("agent-runtime-conv-1") is not None


def test_agent_runtime_casts_string_hire_dates_before_extracting_year(
    monkeypatch, tmp_path: Path
) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-101", "department": "HR", "hire_date": "2024-03-18"},
                {"employee_id": "E-102", "department": "HR", "hire_date": "2026-01-12"},
                {"employee_id": "E-103", "department": "PM", "hire_date": "unknown"},
            ],
        )

        runtime = get_agent_runtime()
        result = runtime.run_turn(
            AgentRequest(
                conversation_id="agent-runtime-conv-string-dates",
                request_id="agent-runtime-req-string-dates",
                user_id="alice",
                project_id="north",
                dataset_table=dataset_table,
                message="柱状图显示入职年份统计",
                role="viewer",
                department="HR",
                clearance=1,
            )
        )

    assert result.final_status == "completed"
    assert result.spec["chart_type"] == "bar"
    assert result.spec["data"] == [
        {"hire_year": 2024, "metric_value": 1},
        {"hire_year": 2026, "metric_value": 1},
    ]
    assert 'TRY_CAST("hire_date" AS DATE)' in str(result.ai_state["latest_result"]["sql"])


def test_agent_runtime_builds_salary_distribution_with_bucketed_sql(
    monkeypatch, tmp_path: Path
) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-201", "department": "HR", "salary": 8200},
                {"employee_id": "E-202", "department": "HR", "salary": 9900},
                {"employee_id": "E-203", "department": "PM", "salary": 15200},
                {"employee_id": "E-204", "department": "PM", "salary": 17900},
            ],
        )

        runtime = get_agent_runtime()
        result = runtime.run_turn(
            AgentRequest(
                conversation_id="agent-runtime-conv-salary-distribution",
                request_id="agent-runtime-req-salary-distribution",
                user_id="alice",
                project_id="north",
                dataset_table=dataset_table,
                message="柱状图显示薪资分布统计",
                role="admin",
                department="HR",
                clearance=9,
            )
        )

    assert result.final_status == "completed"
    assert result.spec["chart_type"] == "bar"
    assert result.spec["title"] == "Salary Distribution"
    assert result.spec["data"] == [
        {"salary_band": "5000-9999", "metric_value": 2},
        {"salary_band": "15000-19999", "metric_value": 2},
    ]
    assert 'FLOOR("salary" / 5000)' in str(result.ai_state["latest_result"]["sql"])


def test_agent_runtime_builds_distribution_for_generic_numeric_columns(
    monkeypatch, tmp_path: Path
) -> None:
    set_agent_env(monkeypatch, tmp_path, chat_engine="agent_primary")

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-301", "department": "HR", "score": 62},
                {"employee_id": "E-302", "department": "HR", "score": 68},
                {"employee_id": "E-303", "department": "PM", "score": 91},
                {"employee_id": "E-304", "department": "PM", "score": 95},
            ],
        )

        runtime = get_agent_runtime()
        result = runtime.run_turn(
            AgentRequest(
                conversation_id="agent-runtime-conv-score-distribution",
                request_id="agent-runtime-req-score-distribution",
                user_id="alice",
                project_id="north",
                dataset_table=dataset_table,
                message="柱状图显示 score 分布统计",
                role="admin",
                department="HR",
                clearance=9,
            )
        )

    assert result.final_status == "completed"
    assert result.spec["chart_type"] == "bar"
    assert result.spec["title"] == "Score Distribution"
    assert result.spec["data"] == [
        {"score_band": "60-69", "metric_value": 2},
        {"score_band": "90-99", "metric_value": 2},
    ]
