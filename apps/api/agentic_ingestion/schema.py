from __future__ import annotations

import sqlite3
from pathlib import Path

M0_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "migrations" / "0003_workspace_agentic_ingestion_init.sql"
)


def read_schema_sql() -> str:
    return M0_SCHEMA_PATH.read_text(encoding="utf-8")


def initialize_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(read_schema_sql())
    connection.commit()
