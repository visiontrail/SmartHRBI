from __future__ import annotations

from pathlib import Path

from apps.api.views import _sqlite_db_path_from_url


def test_sqlite_url_with_relative_dot_path_stays_under_api_dir() -> None:
    path = _sqlite_db_path_from_url("sqlite:///./data/uploads/state/ai_views.sqlite3")

    assert path == (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "api"
        / "data"
        / "uploads"
        / "state"
        / "ai_views.sqlite3"
    ).resolve()


def test_sqlite_url_with_absolute_path_remains_absolute(tmp_path: Path) -> None:
    db_path = tmp_path / "views.db"

    assert _sqlite_db_path_from_url(f"sqlite:///{db_path}") == db_path.resolve()
