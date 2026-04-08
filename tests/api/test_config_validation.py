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
