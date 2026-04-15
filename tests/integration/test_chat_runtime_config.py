from __future__ import annotations

from pathlib import Path

from apps.api.config import get_settings


def test_chat_engine_env_is_ignored(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'views.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CHAT_ENGINE", "legacy_fixed")
    monkeypatch.setenv("CLAUDE_AGENT_SDK_ENABLED", "true")
    get_settings.cache_clear()

    settings = get_settings()

    assert not hasattr(settings, "chat_engine")
