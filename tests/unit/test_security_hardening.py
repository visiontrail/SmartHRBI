from __future__ import annotations

import pytest

from apps.api.security import (
    AccessContext,
    QueryAccessError,
    RLSInjector,
    RLSError,
    SQLGuardError,
    SQLReadOnlyValidator,
    secure_query_sql,
)


def test_security_error_types_expose_structured_detail() -> None:
    assert SQLGuardError(code="GUARD", message="bad").to_detail() == {
        "code": "GUARD",
        "message": "bad",
    }
    assert RLSError(code="RLS", message="scoped").to_detail() == {
        "code": "RLS",
        "message": "scoped",
    }
    assert QueryAccessError(code="ACCESS", message="denied").to_detail() == {
        "code": "ACCESS",
        "message": "denied",
    }


def test_sql_validator_rejects_parse_errors_and_multi_statement_payloads() -> None:
    validator = SQLReadOnlyValidator(allowed_tables={"dataset_scope"})

    with pytest.raises(SQLGuardError) as parse_exc:
        validator.validate("SELECT FROM")
    assert parse_exc.value.code == "SQL_PARSE_ERROR"

    with pytest.raises(SQLGuardError) as multi_exc:
        validator.validate("SELECT 1; SELECT 2")
    assert multi_exc.value.code == "MULTI_STATEMENT_NOT_ALLOWED"


def test_sql_validator_applies_column_whitelist_with_alias_and_cte() -> None:
    validator = SQLReadOnlyValidator(
        allowed_tables={"dataset_scope"},
        allowed_columns_by_table={"dataset_scope": {"department"}},
    )

    # CTE alias itself should not be treated as a physical source table.
    validator.validate(
        "WITH scoped AS (SELECT department FROM dataset_scope) "
        "SELECT department FROM scoped"
    )

    with pytest.raises(SQLGuardError) as exc_info:
        validator.validate("SELECT ds.status FROM dataset_scope AS ds")

    assert exc_info.value.code == "COLUMN_NOT_ALLOWED"


def test_rls_injector_handles_parse_context_and_where_merging() -> None:
    injector = RLSInjector()
    viewer = AccessContext(user_id="u-1", role="viewer", department="HR", clearance=1)

    with pytest.raises(RLSError) as parse_exc:
        injector.inject("SELECT FROM", context=viewer)
    assert parse_exc.value.code == "SQL_PARSE_ERROR"

    with pytest.raises(RLSError) as missing_context_exc:
        injector.inject(
            "SELECT * FROM dataset_scope",
            context=AccessContext(user_id="u-2", role="viewer", department=None, clearance=1),
        )
    assert missing_context_exc.value.code == "RLS_CONTEXT_MISSING"

    with pytest.raises(RLSError) as unsupported_exc:
        injector.inject("DELETE FROM dataset_scope", context=viewer)
    assert unsupported_exc.value.code == "RLS_UNSUPPORTED_QUERY"

    scoped_sql = injector.inject(
        "SELECT * FROM dataset_scope WHERE score > 0",
        context=viewer,
    )
    assert "WHERE" in scoped_sql
    assert "score > 0" in scoped_sql
    assert "department = 'HR'" in scoped_sql
    assert "status = 'active'" in scoped_sql

    # Admin should bypass RLS rewriting entirely.
    original_sql = "SELECT * FROM dataset_scope"
    assert (
        injector.inject(
            original_sql,
            context=AccessContext(user_id="u-admin", role="admin", department="HR", clearance=9),
        )
        == original_sql
    )


def test_rls_injector_skips_department_scoping_for_hr_role() -> None:
    injector = RLSInjector()
    original_sql = "SELECT * FROM dataset_scope"
    assert (
        injector.inject(
            original_sql,
            context=AccessContext(user_id="u-hr", role="hr", department="HR", clearance=1),
        )
        == original_sql
    )
    assert (
        injector.inject(
            original_sql,
            context=AccessContext(user_id="u-hr", role="hr", department=None, clearance=1),
        )
        == original_sql
    )


def test_secure_query_sql_maps_access_denied_and_preserves_guard_errors() -> None:
    guard = SQLReadOnlyValidator(
        allowed_tables={"dataset_scope"},
        sensitive_columns={"salary"},
    )
    injector = RLSInjector()

    with pytest.raises(QueryAccessError) as denied_exc:
        secure_query_sql(
            "SELECT salary FROM dataset_scope",
            context=AccessContext(user_id="u-1", role="viewer", department="HR", clearance=1),
            guard=guard,
            rls_injector=injector,
        )
    assert denied_exc.value.code == "ACCESS_DENIED"

    with pytest.raises(SQLGuardError) as parse_exc:
        secure_query_sql(
            "SELECT FROM",
            context=AccessContext(user_id="u-admin", role="admin", department="HR", clearance=9),
            guard=guard,
            rls_injector=injector,
        )
    assert parse_exc.value.code == "SQL_PARSE_ERROR"
