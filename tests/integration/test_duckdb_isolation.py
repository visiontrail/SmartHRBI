from __future__ import annotations

from pathlib import Path

import pandas as pd

from apps.api.config import get_settings
from apps.api.datasets import clear_dataset_service_cache, get_dataset_service


def _set_minimal_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    clear_dataset_service_cache()


def _seed_table(*, user_id: str, project_id: str, table_name: str, rows: list[dict[str, object]]) -> None:
    service = get_dataset_service(get_settings().upload_dir)
    dataframe = pd.DataFrame(rows)
    with service.session_manager.connection(user_id, project_id) as conn:
        conn.register("seed_df", dataframe)
        conn.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM seed_df')
        conn.unregister("seed_df")


def test_duckdb_session_isolation_between_users(monkeypatch, tmp_path: Path) -> None:
    _set_minimal_env(monkeypatch, tmp_path)

    _seed_table(
        user_id="user-a",
        project_id="project-1",
        table_name="seed_a",
        rows=[
            {"employee_id": "A-1", "department": "HR"},
            {"employee_id": "A-2", "department": "HR"},
        ],
    )
    _seed_table(
        user_id="user-b",
        project_id="project-1",
        table_name="seed_b",
        rows=[
            {"employee_id": "B-1", "department": "PM"},
        ],
    )

    settings = get_settings()
    service = get_dataset_service(settings.upload_dir)

    tables_a = service.list_tables(user_id="user-a", project_id="project-1")
    tables_b = service.list_tables(user_id="user-b", project_id="project-1")

    assert "seed_a" in tables_a
    assert "seed_b" in tables_b
    assert "seed_a" not in tables_b
    assert "seed_b" not in tables_a

    assert (
        service.get_row_count(
            user_id="user-a",
            project_id="project-1",
            table_name="seed_a",
        )
        == 2
    )
    assert (
        service.get_row_count(
            user_id="user-b",
            project_id="project-1",
            table_name="seed_b",
        )
        == 1
    )
