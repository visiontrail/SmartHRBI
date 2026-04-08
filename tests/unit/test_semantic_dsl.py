from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.semantic import SemanticModelValidationError, load_semantic_registry


def test_semantic_dsl_loads_and_validates_builtin_models() -> None:
    registry = load_semantic_registry()

    assert len(registry.metrics) >= 15
    assert "headcount_total" in registry.metrics
    assert "project_count" in registry.metrics

    metric_names = {item["name"] for item in registry.list_metrics()}
    assert "attrition_rate" in metric_names


def test_semantic_dsl_rejects_invalid_metric_entity(tmp_path: Path) -> None:
    broken_model = tmp_path / "broken.yaml"
    broken_model.write_text(
        """
        domain: test
        version: 1
        entities:
          workforce:
            table: workforce
            primary_key: employee_id
            dimensions:
              - name: employee_id
                column: employee_id
                type: string
        metrics:
          - name: bad_metric
            label: Bad Metric
            entity: missing_entity
            kind: count
        """,
        encoding="utf-8",
    )

    with pytest.raises(SemanticModelValidationError) as exc_info:
        load_semantic_registry(tmp_path)

    assert "unknown entity" in exc_info.value.message
