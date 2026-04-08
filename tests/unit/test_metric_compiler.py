from __future__ import annotations

import pytest

from apps.api.semantic import (
    IntentParser,
    MetricCompileError,
    QueryFilter,
    SemanticQueryAST,
    get_metric_compiler,
    get_semantic_registry,
)


def test_metric_compiler_generates_explainable_sql() -> None:
    compiler = get_metric_compiler()

    query_ast = SemanticQueryAST(
        metric="active_employee_count",
        group_by=["department"],
        filters=[QueryFilter(field="status", op="eq", value="active")],
        limit=50,
    )
    compiled = compiler.compile(query_ast, table_override="dataset_snapshot")

    assert 'FROM "dataset_snapshot"' in compiled.sql
    assert 'GROUP BY "department"' in compiled.sql
    assert 'ORDER BY metric_value DESC' in compiled.sql
    assert "LIMIT 50" in compiled.sql
    assert compiled.explain["metric"] == "active_employee_count"
    assert compiled.explain["metric_source"]["entity"] == "workforce"


def test_metric_compiler_parses_intent_to_query_ast() -> None:
    registry = get_semantic_registry()
    parser = IntentParser(registry)

    query_ast = parser.parse("按部门看离职率")

    assert query_ast.metric == "attrition_rate"
    assert query_ast.group_by == ["department"]


def test_metric_compiler_returns_structured_error_for_unknown_metric() -> None:
    compiler = get_metric_compiler()
    query_ast = SemanticQueryAST(metric="not_existing_metric")

    with pytest.raises(MetricCompileError) as exc_info:
        compiler.compile(query_ast, table_override="dataset_snapshot")

    detail = exc_info.value.to_detail()
    assert detail["code"] == "METRIC_NOT_FOUND"
