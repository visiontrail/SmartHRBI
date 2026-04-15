from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.agent_runtime import AgentRequest, clear_agent_runtime_cache, get_agent_runtime
from apps.api.llm_openai import AgentLLMResponse, AgentLLMToolCall
from apps.api.main import app
from tests.agent_test_utils import set_agent_env, upload_dataset


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


def test_agent_runtime_rejects_ungrounded_final_answer_until_model_issues_tool_calls(
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
        observed_messages: list[tuple[int, list[dict[str, object]]]] = []

        class _StubLLM:
            def chat(self, *, messages, conversation_id, step):  # type: ignore[no-untyped-def]
                _ = conversation_id
                observed_messages.append((step, list(messages)))
                if step == 1:
                    return AgentLLMResponse(
                        content=json.dumps(
                            {
                                "chart_type": "bar",
                                "title": "各部门员工年龄分布",
                                "x_key": "department",
                                "y_key": "age",
                                "series_key": None,
                                "metric_name": "avg_age_by_dept",
                                "rows": [{"department": "人力资源部", "age": 32.0}],
                                "conclusion": "编造的答案。",
                                "scope": "未知",
                                "anomalies": "none",
                            },
                            ensure_ascii=False,
                        ),
                        tool_calls=[],
                        finish_reason="stop",
                    )

                if step == 2:
                    return AgentLLMResponse(
                        content="",
                        tool_calls=[
                            AgentLLMToolCall(
                                call_id="call_list_tables_2",
                                tool_name="list_tables",
                                arguments={},
                            )
                        ],
                        finish_reason="tool_calls",
                    )

                return AgentLLMResponse(
                    content=json.dumps(
                        {
                            "chart_type": "bar",
                            "title": "各部门员工年龄分布",
                            "x_key": "department",
                            "y_key": "age",
                            "series_key": None,
                            "metric_name": "avg_age_by_dept",
                            "rows": [
                                {"department": "HR", "age": 29},
                                {"department": "PM", "age": 34},
                            ],
                            "conclusion": "基于工具结果生成。",
                            "scope": "当前数据集 employees_wide 按部门汇总",
                            "anomalies": "none",
                        },
                        ensure_ascii=False,
                    ),
                    tool_calls=[],
                    finish_reason="stop",
                )

        runtime._llm = _StubLLM()  # type: ignore[assignment]
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
    assert len(observed_messages) == 3
    assert not any(message.get("role") == "tool" for message in observed_messages[0][1])
    assert not any(message.get("role") == "tool" for message in observed_messages[1][1])
    assert any(message.get("role") == "tool" for message in observed_messages[2][1])
    tool_uses = [item for item in result.tool_trace if item.get("event") == "tool_use"]
    assert [item["tool_name"] for item in tool_uses] == ["list_tables"]
    assert result.spec["data"] == [
        {"department": "HR", "age": 29},
        {"department": "PM", "age": 34},
    ]
