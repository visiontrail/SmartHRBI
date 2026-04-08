from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.semantic import (
    DimensionDefinition,
    EntityDefinition,
    MetricCompileError,
    MetricCompiler,
    MetricDefinition,
    QueryFilter,
    SemanticModelValidationError,
    SemanticQueryAST,
    SemanticRegistry,
    get_metric_compiler,
    get_semantic_registry,
    load_semantic_registry,
)


def test_metric_compiler_renders_supported_filter_ops_and_literals() -> None:
    compiler = get_metric_compiler()
    entity = get_semantic_registry().entities["workforce"]

    assert compiler._render_filter(QueryFilter(field="status", op="eq", value="active"), entity=entity) == (
        '"status" = \'active\''
    )
    assert compiler._render_filter(QueryFilter(field="status", op="neq", value="inactive"), entity=entity) == (
        '"status" <> \'inactive\''
    )
    assert compiler._render_filter(QueryFilter(field="score", op="gt", value=60), entity=entity) == '"score" > 60'
    assert compiler._render_filter(QueryFilter(field="score", op="gte", value=60), entity=entity) == '"score" >= 60'
    assert compiler._render_filter(QueryFilter(field="score", op="lt", value=60), entity=entity) == '"score" < 60'
    assert compiler._render_filter(QueryFilter(field="score", op="lte", value=60), entity=entity) == '"score" <= 60'
    assert compiler._render_filter(QueryFilter(field="status", op="eq", value=True), entity=entity) == '"status" = TRUE'
    assert compiler._render_filter(QueryFilter(field="status", op="eq", value=None), entity=entity) == '"status" = NULL'

    in_sql = compiler._render_filter(QueryFilter(field="department", op="in", value=["HR", "PM"]), entity=entity)
    assert in_sql == '"department" IN (\'HR\', \'PM\')'


def test_metric_compiler_rejects_invalid_limit_filter_operator_and_identifier() -> None:
    compiler = get_metric_compiler()
    entity = get_semantic_registry().entities["workforce"]

    with pytest.raises(MetricCompileError) as invalid_limit:
        compiler.compile(
            SemanticQueryAST(metric="headcount_total", limit=0),
            table_override="dataset_scope",
        )
    assert invalid_limit.value.code == "INVALID_LIMIT"

    with pytest.raises(MetricCompileError) as invalid_filter_field:
        compiler.compile(
            SemanticQueryAST(metric="headcount_total", filters=[QueryFilter(field="unknown", op="eq", value=1)]),
            table_override="dataset_scope",
        )
    assert invalid_filter_field.value.code == "INVALID_FILTER_FIELD"

    with pytest.raises(MetricCompileError) as invalid_in_value:
        compiler._render_filter(QueryFilter(field="department", op="in", value=[]), entity=entity)
    assert invalid_in_value.value.code == "INVALID_FILTER_VALUE"

    with pytest.raises(MetricCompileError) as invalid_operator:
        compiler._render_filter(QueryFilter(field="department", op="contains", value="HR"), entity=entity)
    assert invalid_operator.value.code == "UNSUPPORTED_FILTER_OP"

    with pytest.raises(MetricCompileError) as invalid_identifier:
        compiler.compile(SemanticQueryAST(metric="headcount_total"), table_override="dataset_scope;drop")
    assert invalid_identifier.value.code == "INVALID_IDENTIFIER"


def test_metric_expression_errors_cover_ratio_cycle_and_missing_column_paths() -> None:
    entity = EntityDefinition(
        name="workforce",
        table="workforce",
        primary_key="employee_id",
        dimensions=[DimensionDefinition(name="employee_id", column="employee_id", type="string")],
    )

    metrics = {
        "bad_ratio": MetricDefinition(
            name="bad_ratio",
            label="Bad Ratio",
            domain="test",
            entity="workforce",
            kind="ratio",
            description="",
            synonyms=[],
        ),
        "bad_sum": MetricDefinition(
            name="bad_sum",
            label="Bad Sum",
            domain="test",
            entity="workforce",
            kind="sum",
            description="",
            synonyms=[],
            column=None,
        ),
        "bad_kind": MetricDefinition(
            name="bad_kind",
            label="Bad Kind",
            domain="test",
            entity="workforce",
            kind="median",
            description="",
            synonyms=[],
            column="employee_id",
        ),
    }

    compiler = MetricCompiler(SemanticRegistry(entities={"workforce": entity}, metrics=metrics))

    with pytest.raises(MetricCompileError) as invalid_ratio:
        compiler._metric_expression(metric_name="bad_ratio", stack=[])
    assert invalid_ratio.value.code == "INVALID_RATIO_METRIC"

    with pytest.raises(MetricCompileError) as missing_column:
        compiler._metric_expression(metric_name="bad_sum", stack=[])
    assert missing_column.value.code == "MISSING_METRIC_COLUMN"

    with pytest.raises(MetricCompileError) as unsupported_kind:
        compiler._metric_expression(metric_name="bad_kind", stack=[])
    assert unsupported_kind.value.code == "UNSUPPORTED_METRIC_KIND"

    with pytest.raises(MetricCompileError) as cyclic:
        compiler._metric_expression(metric_name="bad_sum", stack=["bad_sum"])
    assert cyclic.value.code == "CYCLIC_METRIC"


def test_semantic_registry_validation_errors_for_missing_files_and_invalid_models(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"
    with pytest.raises(SemanticModelValidationError) as missing_exc:
        load_semantic_registry(missing_dir)
    assert "not found" in missing_exc.value.message

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir(parents=True)
    with pytest.raises(SemanticModelValidationError) as empty_exc:
        load_semantic_registry(empty_dir)
    assert "No semantic YAML files" in empty_exc.value.message

    missing_domain_model = tmp_path / "missing_domain.yaml"
    missing_domain_model.write_text(
        """
entities:
  workforce:
    table: workforce
    primary_key: employee_id
    dimensions:
      - name: employee_id
        column: employee_id
        type: string
metrics:
  - name: headcount
    label: Headcount
    entity: workforce
    kind: count_distinct
    column: employee_id
        """,
        encoding="utf-8",
    )
    with pytest.raises(SemanticModelValidationError) as missing_domain_exc:
        load_semantic_registry(tmp_path)
    assert "Missing domain" in missing_domain_exc.value.message
