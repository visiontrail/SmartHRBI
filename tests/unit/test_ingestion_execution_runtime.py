from __future__ import annotations

import pytest

from apps.api.agentic_ingestion.models import DiffPreview, IngestionProposalPayload
from apps.api.agentic_ingestion.runtime import IngestionPlanningError, SQLWriteValidator, WriteIngestionAgentRuntime


def _proposal_payload() -> IngestionProposalPayload:
    return IngestionProposalPayload(
        business_type="roster",
        confidence=0.9,
        recommended_action="update_existing",
        candidate_actions=["update_existing", "new_table", "time_partitioned_new_table", "cancel"],
        target_table="employee_roster",
        time_grain="none",
        match_columns=["employee_id"],
        column_mapping={
            "Employee ID": "employee_id",
            "Name": "employee_name",
            "Department": "department",
        },
        diff_preview=DiffPreview(
            predicted_insert_count=10,
            predicted_update_count=30,
            predicted_conflict_count=2,
        ),
        risks=["2 potential conflicts were detected in dry preview."],
        sql_draft="",
    )


def test_sql_write_validator_accepts_bound_merge_statement() -> None:
    validator = SQLWriteValidator(
        target_table="employee_roster",
        staging_table="staging_123456789abc",
        action_mode="update_existing",
    )
    sql = """
    MERGE INTO employee_roster AS t
    USING staging_123456789abc AS s
    ON t.employee_id = s.employee_id
    WHEN MATCHED THEN UPDATE SET employee_name = s.employee_name
    WHEN NOT MATCHED THEN INSERT (employee_id, employee_name) VALUES (s.employee_id, s.employee_name)
    """

    normalized = validator.validate(sql)
    assert "MERGE INTO employee_roster" in normalized


def test_sql_write_validator_rejects_multi_statement_payload() -> None:
    validator = SQLWriteValidator(
        target_table="employee_roster",
        staging_table="staging_123456789abc",
        action_mode="new_table",
    )

    with pytest.raises(IngestionPlanningError) as exc_info:
        validator.validate("CREATE TABLE employee_roster AS SELECT * FROM staging_123456789abc; SELECT 1")

    assert exc_info.value.code == "WRITE_SQL_MULTI_STATEMENT_NOT_ALLOWED"


def test_sql_write_validator_rejects_target_table_mismatch() -> None:
    validator = SQLWriteValidator(
        target_table="employee_roster",
        staging_table="staging_123456789abc",
        action_mode="new_table",
    )

    with pytest.raises(IngestionPlanningError) as exc_info:
        validator.validate("CREATE TABLE another_table AS SELECT * FROM staging_123456789abc")

    assert exc_info.value.code == "WRITE_SQL_TARGET_MISMATCH"


def test_build_dry_run_summary_exposes_prediction_and_warnings() -> None:
    runtime = WriteIngestionAgentRuntime()
    proposal = _proposal_payload()
    summary = runtime._build_dry_run_summary(  # noqa: SLF001
        proposal_payload=proposal,
        approved_action="update_existing",
        target_table="employee_roster",
        time_grain="none",
    )

    assert summary["predicted_insert_count"] == 10
    assert summary["predicted_update_count"] == 30
    assert summary["predicted_conflict_count"] == 2
    assert summary["predicted_affected_rows"] == 40
    assert summary["target_table"] == "employee_roster"
