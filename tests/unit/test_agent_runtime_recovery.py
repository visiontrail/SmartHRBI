from __future__ import annotations

from apps.api.agent_runtime import _recover_final_answer_from_tool_trace


def test_recover_final_answer_prefers_sql_result_over_later_distinct_values() -> None:
    tool_trace = [
        {
            "event": "tool_result",
            "tool_name": "execute_readonly_sql",
            "status": "success",
            "result": {
                "row_count": 3,
                "rows": [
                    {"age_group": "25-30岁", "employee_count": 8},
                    {"age_group": "30-35岁", "employee_count": 14},
                    {"age_group": "35-40岁", "employee_count": 6},
                ],
            },
        },
        {
            "event": "tool_result",
            "tool_name": "get_distinct_values",
            "status": "success",
            "result": {
                "field": "department",
                "row_count": 2,
                "values": [
                    {"value": "NTN中心", "frequency": 20},
                    {"value": "平台研发", "frequency": 18},
                ],
            },
        },
    ]

    answer = _recover_final_answer_from_tool_trace(
        tool_trace=tool_trace,
        request_message="按年龄段统计员工人数",
    )

    assert answer is not None
    assert answer["chart_type"] == "bar"
    assert answer["title"] == "SQL 查询结果"
    assert answer["x_key"] == "age_group"
    assert answer["y_key"] == "employee_count"
    assert answer["rows"] == tool_trace[0]["result"]["rows"]
    assert answer["anomalies"] == "agent_auto_composed_from_tool_result"


def test_recover_final_answer_returns_none_without_successful_grounding() -> None:
    answer = _recover_final_answer_from_tool_trace(
        tool_trace=[
            {
                "event": "tool_result",
                "tool_name": "execute_readonly_sql",
                "status": "failed",
                "result": {"error": "QUERY_EXECUTION_FAILED"},
            }
        ],
        request_message="按部门统计人数",
    )

    assert answer is None


def test_recover_final_answer_prefers_non_empty_semantic_result_over_empty_sql() -> None:
    tool_trace = [
        {
            "event": "tool_result",
            "tool_name": "execute_readonly_sql",
            "status": "success",
            "result": {
                "row_count": 0,
                "rows": [],
            },
        },
        {
            "event": "tool_result",
            "tool_name": "run_semantic_query",
            "status": "success",
            "result": {
                "metric": "avg_age",
                "row_count": 1,
                "rows": [{"metric_value": None}],
            },
        },
    ]

    answer = _recover_final_answer_from_tool_trace(
        tool_trace=tool_trace,
        request_message="统计平均年龄",
    )

    assert answer is not None
    assert answer["title"] == "avg_age 查询结果"
    assert answer["rows"] == [{"metric_value": None}]
