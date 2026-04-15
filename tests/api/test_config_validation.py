from __future__ import annotations

import pytest

from apps.api.config import get_settings


@pytest.mark.parametrize(
    "missing_key",
    [
        "DATABASE_URL",
        "MODEL_PROVIDER_URL",
        "AUTH_SECRET",
        "LOG_LEVEL",
        "UPLOAD_DIR",
    ],
)
def test_missing_required_env_raises_runtime_error(monkeypatch, missing_key: str, tmp_path) -> None:
    env_file = tmp_path / "api.env"
    env_lines = {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
        "MODEL_PROVIDER_URL": "http://localhost:11434",
        "AUTH_SECRET": "secret",
        "LOG_LEVEL": "INFO",
        "UPLOAD_DIR": "./uploads",
    }
    env_lines.pop(missing_key)
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in env_lines.items()),
        encoding="utf-8",
    )

    monkeypatch.setenv("API_ENV_FILE", str(env_file))
    for key in ["DATABASE_URL", "MODEL_PROVIDER_URL", "AUTH_SECRET", "LOG_LEVEL", "UPLOAD_DIR"]:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError):
        get_settings()


def test_optional_ai_settings_are_loaded_from_env_file(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://user:pass@localhost:5432/db",
                "MODEL_PROVIDER_URL=https://api.openai.com",
                "AI_API_KEY=test-api-key",
                "AI_MODEL=qwen-plus",
                "AI_TIMEOUT_SECONDS=12",
                "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic",
                "ANTHROPIC_AUTH_TOKEN=deepseek-agent-key",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-chat",
                "API_TIMEOUT_MS=600000",
                "AUTH_SECRET=secret",
                "LOG_LEVEL=INFO",
                "UPLOAD_DIR=./uploads",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("API_ENV_FILE", str(env_file))
    for key in [
        "DATABASE_URL",
        "MODEL_PROVIDER_URL",
        "AI_API_KEY",
        "AI_MODEL",
        "AI_TIMEOUT_SECONDS",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "API_TIMEOUT_MS",
        "AUTH_SECRET",
        "LOG_LEVEL",
        "UPLOAD_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.ai_api_key == "test-api-key"
    assert settings.ai_model == "qwen-plus"
    assert settings.ai_timeout_seconds == 12
    assert settings.anthropic_base_url == "https://api.deepseek.com/anthropic"
    assert settings.anthropic_auth_token == "deepseek-agent-key"
    assert settings.anthropic_default_haiku_model == "deepseek-chat"
    assert settings.api_timeout_ms == 600000


def test_agent_engine_requires_claude_agent_sdk_toggle(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / "api.env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://user:pass@localhost:5432/db",
                "MODEL_PROVIDER_URL=https://api.openai.com",
                "CLAUDE_AGENT_SDK_ENABLED=false",
                "AUTH_SECRET=secret",
                "LOG_LEVEL=INFO",
                "UPLOAD_DIR=./uploads",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("API_ENV_FILE", str(env_file))
    for key in [
        "DATABASE_URL",
        "MODEL_PROVIDER_URL",
        "CLAUDE_AGENT_SDK_ENABLED",
        "AUTH_SECRET",
        "LOG_LEVEL",
        "UPLOAD_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError):
        get_settings()
