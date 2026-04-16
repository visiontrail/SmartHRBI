from __future__ import annotations

import sqlite3

from apps.api.agentic_ingestion.schema import initialize_sqlite_schema, read_schema_sql


EXPECTED_TABLES = {
    "users",
    "workspaces",
    "workspace_members",
    "table_catalog",
    "ingestion_uploads",
    "ingestion_jobs",
    "ingestion_proposals",
    "ingestion_executions",
    "ingestion_events",
}


def test_m0_schema_contains_required_tables() -> None:
    schema_sql = read_schema_sql()

    for table_name in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in schema_sql


def test_m0_schema_initializes_sqlite_database() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        initialize_sqlite_schema(connection)
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connection.close()

    created = {name for (name,) in rows}
    missing = EXPECTED_TABLES - created
    assert not missing, f"missing tables: {sorted(missing)}"
