from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE_PATH = Path(__file__).resolve().parent / ".env"
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    app_name: str = Field(default="SmartHRBI API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    model_provider_url: str = Field(alias="MODEL_PROVIDER_URL")
    ai_api_key: str = Field(default="", alias="AI_API_KEY")
    ai_model: str = Field(default="gpt-4o-mini", alias="AI_MODEL")
    ai_timeout_seconds: float = Field(default=20.0, alias="AI_TIMEOUT_SECONDS")
    chat_engine: str = Field(default="agent_primary", alias="CHAT_ENGINE")
    claude_agent_sdk_enabled: bool = Field(default=True, alias="CLAUDE_AGENT_SDK_ENABLED")
    agent_max_tool_steps: int = Field(default=6, alias="AGENT_MAX_TOOL_STEPS")
    agent_max_sql_rows: int = Field(default=200, alias="AGENT_MAX_SQL_ROWS")
    agent_max_sql_scan_rows: int = Field(default=10000, alias="AGENT_MAX_SQL_SCAN_ROWS")
    agent_timeout_seconds: float = Field(default=25.0, alias="AGENT_TIMEOUT_SECONDS")
    auth_secret: str = Field(alias="AUTH_SECRET")
    log_level: str = Field(alias="LOG_LEVEL")
    upload_dir: Path = Field(alias="UPLOAD_DIR")
    cors_allow_origins: str = Field(
        default="http://127.0.0.1:3000,http://localhost:3000",
        alias="CORS_ALLOW_ORIGINS",
    )

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in LOG_LEVELS:
            allowed = ", ".join(sorted(LOG_LEVELS))
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return upper

    @field_validator("upload_dir")
    @classmethod
    def normalize_upload_dir(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (Path(__file__).resolve().parent / value).resolve()

    @field_validator("ai_timeout_seconds")
    @classmethod
    def validate_ai_timeout_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("AI_TIMEOUT_SECONDS must be greater than 0")
        return value

    @field_validator("agent_timeout_seconds")
    @classmethod
    def validate_agent_timeout_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("AGENT_TIMEOUT_SECONDS must be greater than 0")
        return value

    @field_validator("agent_max_tool_steps", "agent_max_sql_rows", "agent_max_sql_scan_rows")
    @classmethod
    def validate_positive_ints(cls, value: int, info) -> int:  # type: ignore[no-untyped-def]
        if value <= 0:
            field_name = str(info.field_name).upper()
            raise ValueError(f"{field_name} must be greater than 0")
        return value

    @field_validator("chat_engine")
    @classmethod
    def validate_chat_engine(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "agent_primary":
            raise ValueError("CHAT_ENGINE must be agent_primary")
        return normalized

    @model_validator(mode="after")
    def validate_agent_engine_sdk_toggle(self) -> "Settings":
        if not self.claude_agent_sdk_enabled:
            raise ValueError("CLAUDE_AGENT_SDK_ENABLED must be true for agent_primary")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env_file_override = os.getenv("API_ENV_FILE")
    env_file = (
        Path(env_file_override).expanduser().resolve()
        if env_file_override
        else DEFAULT_ENV_FILE_PATH
    )
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid API configuration: {exc}") from exc
