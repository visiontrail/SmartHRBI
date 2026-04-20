from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from apps.api.agentic_ingestion.runtime import (
    INGESTION_AGENT_SYSTEM_PROMPT,
    MIN_INGESTION_AGENT_MAX_TURNS,
    IngestionPlanningError,
    WriteIngestionAgentRuntime,
)
from apps.api.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_test() -> Iterator[None]:
    yield
    get_settings.cache_clear()


def _set_runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'workspace-state.db'}")
    monkeypatch.setenv("MODEL_PROVIDER_URL", "http://localhost:11434")
    monkeypatch.setenv("AI_API_KEY", "test-ai-key")
    monkeypatch.setenv("AI_MODEL", "deepseek-chat")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()


def test_ingestion_sdk_turn_budget_covers_full_proposal_sequence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_runtime_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_MAX_TOOL_STEPS", "6")
    get_settings.cache_clear()

    runtime = WriteIngestionAgentRuntime()
    conn = sqlite3.connect(":memory:")
    try:
        options = runtime._build_ingestion_sdk_options(  # noqa: SLF001
            conn=conn,
            job_id="job-demo",
            tool_trace=[],
        )
    finally:
        conn.close()

    assert options.max_turns == MIN_INGESTION_AGENT_MAX_TURNS
    assert options.max_turns > 6


def test_ingestion_system_prompt_keeps_approval_after_preview_and_sql() -> None:
    expected_sequence = (
        "build_diff_preview, generate_write_sql_draft, request_human_approval, "
        "then the final"
    )

    assert expected_sequence in INGESTION_AGENT_SYSTEM_PROMPT


def test_ingestion_sdk_error_result_is_reported_as_ai_unavailable() -> None:
    with pytest.raises(IngestionPlanningError) as exc_info:
        WriteIngestionAgentRuntime._consume_ingestion_sdk_message(  # noqa: SLF001
            message=ResultMessage(
                subtype="error_max_turns",
                duration_ms=1000,
                duration_api_ms=500,
                is_error=True,
                num_turns=6,
                session_id="session-demo",
            ),
            text_blocks=[],
        )

    assert exc_info.value.code == "INGESTION_AI_UNAVAILABLE"
    assert exc_info.value.status_code == 503
    assert "error_max_turns" in exc_info.value.message
