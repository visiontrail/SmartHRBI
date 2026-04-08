from __future__ import annotations

import pytest

from apps.api.security import SQLGuardError, SQLReadOnlyValidator


def test_ast_guard_allows_readonly_select() -> None:
    validator = SQLReadOnlyValidator(allowed_tables={"dataset_1"})

    validator.validate('SELECT department, COUNT(*) FROM dataset_1 GROUP BY department')


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE dataset_1",
        "DELETE FROM dataset_1",
        "UPDATE dataset_1 SET department='HR'",
        "INSERT INTO dataset_1 VALUES (1)",
    ],
)
def test_ast_guard_blocks_non_select_sql(sql: str) -> None:
    validator = SQLReadOnlyValidator(allowed_tables={"dataset_1"})

    with pytest.raises(SQLGuardError) as exc_info:
        validator.validate(sql)

    assert exc_info.value.code == "READ_ONLY_ONLY_SELECT"


def test_ast_guard_blocks_restricted_table_and_column() -> None:
    validator = SQLReadOnlyValidator(
        allowed_tables={"dataset_1"},
        sensitive_tables={"raw_payroll"},
        sensitive_columns={"salary"},
    )

    with pytest.raises(SQLGuardError) as table_exc:
        validator.validate("SELECT * FROM raw_payroll")
    assert table_exc.value.code in {"TABLE_FORBIDDEN", "TABLE_NOT_ALLOWED"}

    with pytest.raises(SQLGuardError) as column_exc:
        validator.validate("SELECT salary FROM dataset_1")
    assert column_exc.value.code == "COLUMN_FORBIDDEN"
