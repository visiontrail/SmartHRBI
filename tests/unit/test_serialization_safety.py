from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from apps.api.agent_runtime import AgentSessionState, AgentSessionStore
from apps.api.chat import ChatEvent, _format_sse


def test_agent_session_store_serializes_datetime_in_tool_trace(tmp_path: Path) -> None:
    store = AgentSessionStore(db_path=tmp_path / "agent_sessions.sqlite3")
    state = AgentSessionState(
        conversation_id="conv-datetime-save",
        agent_session_id="session-datetime-save",
        last_tool_trace=[
            {
                "event": "tool_result",
                "result": {
                    "sample_rows": [
                        {
                            "employee_id": "E-001",
                            "hire_date": datetime(2024, 1, 2, 3, 4, 5),
                        }
                    ]
                },
            }
        ],
    )

    store.save(state)
    reloaded = store.load("conv-datetime-save")

    assert reloaded is not None
    assert reloaded.last_tool_trace[0]["result"]["sample_rows"][0]["hire_date"] == "2024-01-02 03:04:05"


def test_format_sse_serializes_datetime_payload() -> None:
    frame = _format_sse(
        ChatEvent(
            id=1,
            type="tool_result",
            payload={
                "result": {
                    "rows": [
                        {
                            "employee_id": "E-001",
                            "hire_date": datetime(2024, 1, 2, 3, 4, 5),
                        }
                    ]
                }
            },
        )
    )

    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.split(": ", 1)[1])

    assert payload["result"]["rows"][0]["hire_date"] == "2024-01-02 03:04:05"
