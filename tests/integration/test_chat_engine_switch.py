from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.config import get_settings


@pytest.mark.parametrize("deprecated_engine", ["legacy_fixed", "legacy_shadow"])
def test_deprecated_chat_engines_are_rejected(
    monkeypatch,
    tmp_path: Path,
    deprecated_engine: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'views.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CHAT_ENGINE", deprecated_engine)
    monkeypatch.setenv("CLAUDE_AGENT_SDK_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError):
        get_settings()


def test_chat_engine_defaults_to_agent_primary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'views.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("CHAT_ENGINE", raising=False)
    monkeypatch.delenv("CLAUDE_AGENT_SDK_ENABLED", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.chat_engine == "agent_primary"
