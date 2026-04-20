from __future__ import annotations

import re
import sqlite3
from typing import Any

from apps.api.agentic_ingestion.models import IngestionAgentPlanOutput, IngestionProposalPayload
from apps.api.agentic_ingestion.runtime import WriteIngestionAgentRuntime


def install_mock_planning_agent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        WriteIngestionAgentRuntime,
        "_run_planning_agent_loop",
        _mock_run_planning_agent_loop,
    )


def install_failing_planning_agent(  # type: ignore[no-untyped-def]
    monkeypatch,
    *,
    code: str,
    message: str,
    status_code: int,
) -> None:
    from apps.api.agentic_ingestion.runtime import IngestionPlanningError

    failure_message = message

    def _raise(
        self: WriteIngestionAgentRuntime,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
        upload_id: str,
        requested_by: str,
        conversation_id: str | None,
        message: str | None,
    ) -> tuple[IngestionAgentPlanOutput, list[dict[str, Any]]]:
        _ = (self, conn, workspace_id, job_id, upload_id, requested_by, conversation_id, message)
        raise IngestionPlanningError(code=code, message=failure_message, status_code=status_code)

    monkeypatch.setattr(WriteIngestionAgentRuntime, "_run_planning_agent_loop", _raise)


def _mock_run_planning_agent_loop(
    self: WriteIngestionAgentRuntime,
    *,
    conn: sqlite3.Connection,
    workspace_id: str,
    job_id: str,
    upload_id: str,
    requested_by: str,
    conversation_id: str | None,
    message: str | None,
) -> tuple[IngestionAgentPlanOutput, list[dict[str, Any]]]:
    _ = (requested_by, conversation_id, message)
    tool_trace: list[dict[str, Any]] = []
    upload_info = self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="inspect_upload",
        arguments={"upload_id": upload_id},
        handler=lambda: self._tool_inspect_upload(conn=conn, upload_id=upload_id),  # noqa: SLF001
    )
    catalog = self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="get_workspace_catalog",
        arguments={"workspace_id": workspace_id},
        handler=lambda: self._tool_get_workspace_catalog(conn=conn, workspace_id=workspace_id),  # noqa: SLF001
    )
    self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="list_existing_tables",
        arguments={"workspace_id": workspace_id},
        handler=lambda: self._tool_list_existing_tables(conn=conn, workspace_id=workspace_id),  # noqa: SLF001
    )

    agent_guess = {
        "business_type": "roster",
        "confidence": 0.91,
        "reasoning": "Mock agent selected roster from workbook structure.",
    }
    entries = list(catalog.get("entries", []))
    if not entries:
        first_columns = list(upload_info["column_summary"].get("all_columns", []))[:3]
        match_columns = [_normalize_identifier(first_columns[0])] if first_columns else ["employee_id"]
        seed = {
            "business_type": "roster",
            "table_name": "employee_roster",
            "human_label": "Employee Roster",
            "write_mode": "update_existing",
            "time_grain": "none",
            "primary_keys": match_columns,
            "match_columns": match_columns,
            "is_active_target": True,
            "description": "Mock agent seed from upload inspection.",
        }
        human_approval = self._run_tool(  # noqa: SLF001
            conn=conn,
            job_id=job_id,
            trace=tool_trace,
            name="request_human_approval",
            arguments={
                "stage": "catalog_setup",
                "question": "Approve catalog setup before planning the write?",
                "options": ["confirm_catalog_setup", "cancel"],
                "recommended_option": "confirm_catalog_setup",
            },
            handler=lambda: self._tool_request_human_approval(  # noqa: SLF001
                conn=conn,
                job_id=job_id,
                arguments={
                    "stage": "catalog_setup",
                    "question": "Approve catalog setup before planning the write?",
                    "options": ["confirm_catalog_setup", "cancel"],
                    "recommended_option": "confirm_catalog_setup",
                },
            ),
        )
        output = IngestionAgentPlanOutput.model_validate(
            {
                "status": "awaiting_catalog_setup",
                "agent_guess": agent_guess,
                "setup_questions": [
                    {
                        "question_id": "business_type",
                        "title": "这份数据属于哪类业务？",
                        "options": ["roster", "project_progress", "attendance", "other"],
                    },
                    {
                        "question_id": "write_mode",
                        "title": "默认写入方式是什么？",
                        "options": ["update_existing", "time_partitioned_new_table", "new_table"],
                    },
                    {
                        "question_id": "match_columns",
                        "title": "用于匹配更新的主键列是什么？",
                        "options": first_columns,
                    },
                ],
                "suggested_catalog_seed": seed,
                "human_approval": human_approval,
            }
        )
        return output, tool_trace

    target = entries[0]
    schema = self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="describe_table_schema",
        arguments={"workspace_id": workspace_id, "table_name": target["table_name"]},
        handler=lambda: self._tool_describe_table_schema_by_name(  # noqa: SLF001
            conn=conn,
            workspace_id=workspace_id,
            table_name=str(target["table_name"]),
        ),
    )
    action = str(target.get("write_mode") or "update_existing")
    if action not in {"update_existing", "time_partitioned_new_table", "new_table"}:
        action = "update_existing"
    match_columns = list(target.get("match_columns") or target.get("primary_keys") or ["employee_id"])
    diff_preview = self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="build_diff_preview",
        arguments={"upload_id": upload_id, "match_columns": match_columns, "action_mode": action},
        handler=lambda: self._tool_build_diff_preview(  # noqa: SLF001
            upload_info=upload_info,
            match_columns=match_columns,
            action_mode=action,
        ),
    )
    sql_draft = self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="generate_write_sql_draft",
        arguments={
            "workspace_id": workspace_id,
            "job_id": job_id,
            "target_table": target["table_name"],
            "action_mode": action,
            "match_columns": match_columns,
        },
        handler=lambda: self._tool_generate_write_sql_draft(  # noqa: SLF001
            workspace_id=workspace_id,
            job_id=job_id,
            target_table=str(target["table_name"]),
            action_mode=action,
            match_columns=match_columns,
        ),
    )
    human_approval = self._run_tool(  # noqa: SLF001
        conn=conn,
        job_id=job_id,
        trace=tool_trace,
        name="request_human_approval",
        arguments={
            "stage": "proposal_approval",
            "question": "Approve the next ingestion action?",
            "options": ["update_existing", "time_partitioned_new_table", "new_table", "cancel"],
            "recommended_option": action,
        },
        handler=lambda: self._tool_request_human_approval(  # noqa: SLF001
            conn=conn,
            job_id=job_id,
            arguments={
                "stage": "proposal_approval",
                "question": "Approve the next ingestion action?",
                "options": ["update_existing", "time_partitioned_new_table", "new_table", "cancel"],
                "recommended_option": action,
            },
        ),
    )
    proposal = IngestionProposalPayload(
        business_type=str(schema["business_type"]),
        confidence=0.91,
        recommended_action=action,
        candidate_actions=["update_existing", "time_partitioned_new_table", "new_table", "cancel"],
        target_table=str(target["table_name"]),
        time_grain=str(schema["time_grain"]),
        match_columns=match_columns,
        column_mapping={
            str(column): _normalize_identifier(str(column))
            for column in upload_info["column_summary"].get("all_columns", [])
            if str(column).strip()
        },
        diff_preview=diff_preview,
        risks=[],
        explanation="Mock agent proposal generated through the ingestion tool surface.",
        sql_draft=str(sql_draft["sql_draft"]),
        requires_catalog_setup=False,
    )
    output = IngestionAgentPlanOutput.model_validate(
        {
            "status": "awaiting_user_approval",
            "agent_guess": agent_guess,
            "proposal": proposal.model_dump(mode="json"),
            "human_approval": human_approval,
        }
    )
    return output, tool_trace


def _normalize_identifier(raw: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip().lower()).strip("_")
    if not normalized:
        return ""
    if normalized[0].isdigit():
        normalized = f"c_{normalized}"
    return normalized
