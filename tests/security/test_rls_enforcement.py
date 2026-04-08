from __future__ import annotations

import duckdb
import pytest

from apps.api.security import (
    AccessContext,
    QueryAccessError,
    RLSInjector,
    SQLReadOnlyValidator,
    secure_query_sql,
)


def _seed_connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE dataset_scope (
            employee_id VARCHAR,
            department VARCHAR,
            status VARCHAR,
            salary DOUBLE
        )
        """
    )
    conn.execute(
        """
        INSERT INTO dataset_scope VALUES
            ('E-001', 'HR', 'active', 1000),
            ('E-002', 'HR', 'inactive', 1100),
            ('E-003', 'PM', 'active', 1200),
            ('E-004', 'PM', 'active', 1300)
        """
    )
    return conn


def test_rls_injector_returns_scoped_results_by_role() -> None:
    conn = _seed_connection()
    guard = SQLReadOnlyValidator(allowed_tables={"dataset_scope"})
    injector = RLSInjector()

    base_sql = "SELECT department, COUNT(*) AS cnt FROM dataset_scope GROUP BY department ORDER BY department"

    admin_sql = secure_query_sql(
        base_sql,
        context=AccessContext(user_id="u-admin", role="admin", department="HR", clearance=9),
        guard=guard,
        rls_injector=injector,
    )
    viewer_sql = secure_query_sql(
        base_sql,
        context=AccessContext(user_id="u-view", role="viewer", department="HR", clearance=1),
        guard=guard,
        rls_injector=injector,
    )

    admin_rows = conn.execute(admin_sql).fetchall()
    viewer_rows = conn.execute(viewer_sql).fetchall()

    assert admin_rows == [("HR", 2), ("PM", 2)]
    assert viewer_rows == [("HR", 1)]



def test_rls_security_error_message_is_readable_without_leaking_details() -> None:
    guard = SQLReadOnlyValidator(
        allowed_tables={"dataset_scope"},
        sensitive_columns={"salary"},
    )
    injector = RLSInjector()

    with pytest.raises(QueryAccessError) as exc_info:
        secure_query_sql(
            "SELECT salary FROM dataset_scope",
            context=AccessContext(user_id="u-1", role="viewer", department="HR", clearance=1),
            guard=guard,
            rls_injector=injector,
        )

    assert exc_info.value.code == "ACCESS_DENIED"
    assert "scope" in exc_info.value.message.lower()
    assert "salary" not in exc_info.value.message.lower()
