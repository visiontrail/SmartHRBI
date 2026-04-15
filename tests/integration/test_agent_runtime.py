from __future__ import annotations
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.agent_runtime import AgentRequest, clear_agent_runtime_cache, get_agent_runtime
from apps.api.main import app
from tests.agent_test_utils import install_scripted_sdk_client, set_agent_env, upload_dataset


def _sql_tool_call(rows: list[dict[str, object]], sql: str) -> dict[str, object]:
    return {
        "name": "execute_readonly_sql",
        "arguments": {"sql": sql, "max_rows": 200},
        "result": {"rows": rows, "sql": sql},
    }


def test_agent_runtime_supports_single_turn_follow_up_and_restart_recovery(monkeypatch, tmp_path: Path) -> None:
    set_agent_env(monkeypatch, tmp_path)

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
        first_rows = [
            {"hire_year": 2022, "metric_value": 1},
            {"hire_year": 2023, "metric_value": 1},
        ]

        def scenario(prompt: str, options) -> dict[str, object]:  # type: ignore[no-untyped-def]
            _ = options
            if "折线图" in prompt:
                return {
                    "tool_calls": [],
                    "final_answer": {
                        "chart_type": "line",
                        "title": "入职年份统计",
                        "x_key": "hire_year",
                        "y_key": "metric_value",
                        "series_key": None,
                        "metric_name": "headcount",
                        "rows": first_rows,
                        "conclusion": "沿用上一轮查询结果并切换为折线图。",
                        "scope": "当前数据集按入职年份统计",
                        "anomalies": "none",
                    },
                }
            return {
                "tool_calls": [
                    _sql_tool_call(
                        first_rows,
                        'SELECT "hire_year", COUNT(*) AS metric_value FROM dataset GROUP BY "hire_year"',
                    )
                ],
                "final_answer": {
                    "chart_type": "bar",
                    "title": "入职年份统计",
                    "x_key": "hire_year",
                    "y_key": "metric_value",
                    "series_key": None,
                    "metric_name": "headcount",
                    "rows": first_rows,
                    "conclusion": "按入职年份统计员工数。",
                    "scope": "当前数据集按入职年份统计",
                    "anomalies": "none",
                },
            }

        install_scripted_sdk_client(runtime, scenario)
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
    install_scripted_sdk_client(recovered_runtime, scenario)
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
    set_agent_env(monkeypatch, tmp_path)

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
        rows = [
            {"hire_year": 2024, "metric_value": 1},
            {"hire_year": 2026, "metric_value": 1},
        ]
        sql = (
            'SELECT EXTRACT(year FROM TRY_CAST("hire_date" AS DATE)) AS hire_year, '
            'COUNT(*) AS metric_value FROM dataset GROUP BY hire_year'
        )
        install_scripted_sdk_client(
            runtime,
            lambda prompt, options: {  # type: ignore[no-untyped-def]
                "tool_calls": [_sql_tool_call(rows, sql)],
                "final_answer": {
                    "chart_type": "bar",
                    "title": "入职年份统计",
                    "x_key": "hire_year",
                    "y_key": "metric_value",
                    "series_key": None,
                    "metric_name": "headcount",
                    "rows": rows,
                    "conclusion": "按字符串日期转日期后统计。",
                    "scope": "当前数据集按入职年份统计",
                    "anomalies": "none",
                    "sql": sql,
                },
            },
        )
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
    set_agent_env(monkeypatch, tmp_path)

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
        rows = [
            {"salary_band": "5000-9999", "metric_value": 2},
            {"salary_band": "15000-19999", "metric_value": 2},
        ]
        sql = (
            'SELECT CONCAT(CAST(FLOOR("salary" / 5000) * 5000 AS VARCHAR), '
            '\'-\', CAST(FLOOR("salary" / 5000) * 5000 + 4999 AS VARCHAR)) AS salary_band, '
            'COUNT(*) AS metric_value FROM dataset GROUP BY salary_band'
        )
        install_scripted_sdk_client(
            runtime,
            lambda prompt, options: {  # type: ignore[no-untyped-def]
                "tool_calls": [_sql_tool_call(rows, sql)],
                "final_answer": {
                    "chart_type": "bar",
                    "title": "Salary Distribution",
                    "x_key": "salary_band",
                    "y_key": "metric_value",
                    "series_key": None,
                    "metric_name": "salary_distribution",
                    "rows": rows,
                    "conclusion": "薪资按区间聚合。",
                    "scope": "当前数据集薪资分布",
                    "anomalies": "none",
                    "sql": sql,
                },
            },
        )
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
    set_agent_env(monkeypatch, tmp_path)

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
        rows = [
            {"score_band": "60-69", "metric_value": 2},
            {"score_band": "90-99", "metric_value": 2},
        ]
        sql = (
            'SELECT CONCAT(CAST(FLOOR("score" / 10) * 10 AS VARCHAR), '
            '\'-\', CAST(FLOOR("score" / 10) * 10 + 9 AS VARCHAR)) AS score_band, '
            'COUNT(*) AS metric_value FROM dataset GROUP BY score_band'
        )
        install_scripted_sdk_client(
            runtime,
            lambda prompt, options: {  # type: ignore[no-untyped-def]
                "tool_calls": [_sql_tool_call(rows, sql)],
                "final_answer": {
                    "chart_type": "bar",
                    "title": "Score Distribution",
                    "x_key": "score_band",
                    "y_key": "metric_value",
                    "series_key": None,
                    "metric_name": "score_distribution",
                    "rows": rows,
                    "conclusion": "score 按区间聚合。",
                    "scope": "当前数据集 score 分布",
                    "anomalies": "none",
                    "sql": sql,
                },
            },
        )
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


def test_agent_runtime_rejects_ungrounded_final_answer_without_sdk_tool_use(
    monkeypatch, tmp_path: Path
) -> None:
    set_agent_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        dataset_table = upload_dataset(
            client,
            rows=[
                {"employee_id": "E-401", "department": "HR", "age": 29},
                {"employee_id": "E-402", "department": "PM", "age": 34},
            ],
        )

        runtime = get_agent_runtime()
        install_scripted_sdk_client(
            runtime,
            lambda prompt, options: {  # type: ignore[no-untyped-def]
                "tool_calls": [],
                "final_answer": {
                    "chart_type": "bar",
                    "title": "各部门员工年龄分布",
                    "x_key": "department",
                    "y_key": "age",
                    "series_key": None,
                    "metric_name": "avg_age_by_dept",
                    "rows": [{"department": "人力资源部", "age": 32.0}],
                    "conclusion": "未经过工具观测的答案。",
                    "scope": "未知",
                    "anomalies": "none",
                },
            },
        )
        result = runtime.run_turn(
            AgentRequest(
                conversation_id="agent-runtime-conv-ungrounded-answer",
                request_id="agent-runtime-req-ungrounded-answer",
                user_id="alice",
                project_id="north",
                dataset_table=dataset_table,
                message="请使用柱状图呈现部门员工年龄分布",
                role="viewer",
                department="HR",
                clearance=1,
            )
        )

    assert result.final_status == "completed"
    assert result.spec["chart_type"] == "empty"
    assert result.ai_state["latest_result"]["anomalies"] == "no_grounded_tool_observation"
    assert not any(item.get("event") == "tool_use" for item in result.tool_trace)
