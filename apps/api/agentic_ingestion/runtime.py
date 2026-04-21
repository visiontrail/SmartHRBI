from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
import duckdb
import pandas as pd
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolAnnotations,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from ..config import get_settings
from .models import (
    IngestionAgentPlanOutput,
    IngestionApprovalOverrides,
    IngestionCatalogSetupSeed,
    IngestionProposalPayload,
)
from .routing import RouteDecision, select_agent_route

logger = logging.getLogger("smarthrbi.ingestion")

SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORBIDDEN_WRITE_EXPRESSIONS: tuple[type[exp.Expression], ...] = (
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Delete,
)
DEFAULT_ACTION_OPTIONS = [
    "update_existing",
    "time_partitioned_new_table",
    "new_table",
    "cancel",
]
CATALOG_SETUP_APPROVAL_OPTIONS = ["confirm_catalog_setup", "cancel"]
INGESTION_SDK_MCP_SERVER_NAME = "ingestion"
INGESTION_SDK_RUNTIME_BACKEND = "claude-agent-sdk"
INGESTION_APPROVAL_TOOL_NAME = "AskUserQuestion"
INGESTION_LEGACY_APPROVAL_TOOL_NAME = "request_human_approval"
INGESTION_APPROVAL_TOOL_ALIASES = frozenset(
    {
        INGESTION_APPROVAL_TOOL_NAME,
        INGESTION_LEGACY_APPROVAL_TOOL_NAME,
    }
)
INGESTION_AGENT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_workspace_catalog",
        "description": (
            "List workspace catalog entries that describe known writable targets, "
            "business types, write modes, primary keys, and match columns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
            },
            "required": ["workspace_id"],
        },
        "read_only": True,
    },
    {
        "name": "list_existing_tables",
        "description": "List writable table names known for the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
            },
            "required": ["workspace_id"],
        },
        "read_only": True,
    },
    {
        "name": "inspect_upload",
        "description": "Inspect the uploaded workbook metadata, sheets, columns, and sample preview.",
        "parameters": {
            "type": "object",
            "properties": {
                "upload_id": {"type": "string"},
            },
            "required": ["upload_id"],
        },
        "read_only": True,
    },
    {
        "name": "describe_table_schema",
        "description": "Describe one catalog target's configured writable schema contract.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "table_name": {"type": "string"},
            },
            "required": ["workspace_id", "table_name"],
        },
        "read_only": True,
    },
    {
        "name": "build_diff_preview",
        "description": (
            "Build a bounded dry preview for the proposed action using the upload row counts "
            "and proposed match columns. This estimates inserts, updates, and conflicts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "upload_id": {"type": "string"},
                "match_columns": {"type": "array", "items": {"type": "string"}},
                "action_mode": {"type": "string", "enum": DEFAULT_ACTION_OPTIONS},
            },
            "required": ["upload_id", "action_mode"],
        },
        "read_only": True,
    },
    {
        "name": "generate_write_sql_draft",
        "description": (
            "Generate a draft SQL shape for the proposed write action. The draft is explanatory; "
            "execution will later rebuild and validate SQL after human approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "job_id": {"type": "string"},
                "target_table": {"type": "string"},
                "action_mode": {"type": "string", "enum": DEFAULT_ACTION_OPTIONS},
                "match_columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["workspace_id", "job_id", "target_table", "action_mode"],
        },
        "read_only": True,
    },
    {
        "name": INGESTION_APPROVAL_TOOL_NAME,
        "description": (
            "AskUserQuestion for product Human-in-the-Loop approval. The agent must call this "
            "before returning a setup request or a write proposal. This tool never approves; it "
            "records the question and returns that approval is pending."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": ["catalog_setup", "proposal_approval"]},
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "recommended_option": {"type": "string"},
            },
            "required": ["stage", "question", "options"],
        },
        "read_only": False,
    },
]
INGESTION_SDK_TOOL_NAMES = tuple(str(item["name"]) for item in INGESTION_AGENT_TOOL_DEFINITIONS)
INGESTION_SDK_ALLOWED_TOOL_NAMES = tuple(
    f"mcp__{INGESTION_SDK_MCP_SERVER_NAME}__{name}" for name in INGESTION_SDK_TOOL_NAMES
)
INGESTION_AGENT_PROPOSAL_TOOL_SEQUENCE = [
    "inspect_upload",
    "get_workspace_catalog",
    "list_existing_tables",
    "describe_table_schema",
    "build_diff_preview",
    "generate_write_sql_draft",
    INGESTION_APPROVAL_TOOL_NAME,
]
MIN_INGESTION_AGENT_MAX_TURNS = len(INGESTION_AGENT_PROPOSAL_TOOL_SEQUENCE) + 2
INGESTION_AGENT_SYSTEM_PROMPT = """\
You are SmartHRBI's Write Ingestion Agent.

The application has already routed this request to you through select_agent_route.
Do not rely on hidden business rules. Use the provided tools to inspect the upload,
workspace catalog, existing targets, and proposed diff before you decide what should
happen next.

Allowed decisions:
- awaiting_catalog_setup: choose this when the workspace catalog is insufficient for
  a confident writable target. Return setup_questions and suggested_catalog_seed.
- awaiting_user_approval: choose this when you can produce a concrete write proposal.
  Return proposal with business_type, confidence, recommended_action, candidate_actions,
  target_table, match_columns, column_mapping, diff_preview, risks, explanation, and
  sql_draft.

Human approval is mandatory:
- Before awaiting_catalog_setup, call AskUserQuestion with stage=catalog_setup
  and options restricted to confirm_catalog_setup or cancel.
- Before awaiting_user_approval, first complete build_diff_preview and
  generate_write_sql_draft, then call AskUserQuestion with
  stage=proposal_approval and options restricted to update_existing,
  time_partitioned_new_table, new_table, or cancel.
- Never claim approval has happened. The front-end approval card and /ingestion/approve
  endpoint are the only approval mechanisms.

For an existing-table proposal, use this exact order whenever the target table is known:
inspect_upload, get_workspace_catalog, list_existing_tables, describe_table_schema,
build_diff_preview, generate_write_sql_draft, AskUserQuestion, then the final
structured output.

Do not execute writes. Do not invent tool results. Return only the required structured output.
"""


class IngestionPlanningError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(slots=True)
class SQLWriteValidator:
    target_table: str
    staging_table: str
    action_mode: str

    def validate(self, sql: str) -> str:
        normalized_sql = sql.strip()
        if not normalized_sql:
            raise IngestionPlanningError(
                code="WRITE_SQL_REQUIRED",
                message="Approved SQL is empty",
                status_code=422,
            )

        try:
            statements = parse(normalized_sql, read="duckdb")
        except ParseError as exc:
            raise IngestionPlanningError(
                code="WRITE_SQL_PARSE_ERROR",
                message="Approved SQL has invalid syntax",
                status_code=422,
            ) from exc

        if len(statements) != 1:
            raise IngestionPlanningError(
                code="WRITE_SQL_MULTI_STATEMENT_NOT_ALLOWED",
                message="Only one write statement is allowed",
                status_code=422,
            )
        statement = statements[0]
        self._assert_statement_type(statement)
        self._assert_forbidden_operations(statement)
        self._assert_target_binding(statement)
        self._assert_table_scope(statement)
        return normalized_sql

    def _assert_statement_type(self, statement: exp.Expression) -> None:
        if self.action_mode == "update_existing":
            if not isinstance(statement, exp.Merge):
                raise IngestionPlanningError(
                    code="WRITE_SQL_ACTION_MISMATCH",
                    message="update_existing action requires MERGE statement",
                    status_code=422,
                )
            return

        if self.action_mode in {"new_table", "time_partitioned_new_table"}:
            if not isinstance(statement, exp.Create):
                raise IngestionPlanningError(
                    code="WRITE_SQL_ACTION_MISMATCH",
                    message=f"{self.action_mode} action requires CREATE TABLE AS statement",
                    status_code=422,
                )
            return

        raise IngestionPlanningError(
            code="WRITE_ACTION_UNSUPPORTED",
            message=f"Unsupported approved action: {self.action_mode}",
            status_code=422,
        )

    def _assert_forbidden_operations(self, statement: exp.Expression) -> None:
        for node_type in FORBIDDEN_WRITE_EXPRESSIONS:
            if list(statement.find_all(node_type)):
                raise IngestionPlanningError(
                    code="WRITE_SQL_OPERATION_FORBIDDEN",
                    message="Approved SQL contains forbidden operation",
                    status_code=422,
                )

    def _assert_target_binding(self, statement: exp.Expression) -> None:
        if isinstance(statement, exp.Merge):
            target = statement.this
            if not isinstance(target, exp.Table):
                raise IngestionPlanningError(
                    code="WRITE_SQL_TARGET_MISSING",
                    message="MERGE statement must include a target table",
                    status_code=422,
                )
            target_name = target.name.lower()
            if target_name != self.target_table:
                raise IngestionPlanningError(
                    code="WRITE_SQL_TARGET_MISMATCH",
                    message="Approved SQL target table does not match approved proposal",
                    status_code=422,
                )
            return

        if isinstance(statement, exp.Create):
            target = statement.this
            if not isinstance(target, exp.Table):
                raise IngestionPlanningError(
                    code="WRITE_SQL_TARGET_MISSING",
                    message="CREATE statement must include a target table",
                    status_code=422,
                )
            target_name = target.name.lower()
            if target_name != self.target_table:
                raise IngestionPlanningError(
                    code="WRITE_SQL_TARGET_MISMATCH",
                    message="Approved SQL target table does not match approved proposal",
                    status_code=422,
                )

    def _assert_table_scope(self, statement: exp.Expression) -> None:
        allowed = {self.target_table, self.staging_table}
        for table in statement.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name not in allowed:
                raise IngestionPlanningError(
                    code="WRITE_SQL_TABLE_NOT_ALLOWED",
                    message=f"Approved SQL touches table outside execution scope: {table_name}",
                    status_code=422,
                )


@dataclass(slots=True)
class WriteIngestionAgentRuntime:
    stage: str = "M6"

    def health_summary(self) -> str:
        return "Write ingestion runtime supports setup/planning/approval/execution lifecycle"

    def build_plan(
        self,
        *,
        workspace_id: str,
        job_id: str,
        requested_by: str,
        conversation_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = workspace_id.strip()
        normalized_job_id = job_id.strip()
        normalized_requested_by = requested_by.strip()
        normalized_conversation_id = (conversation_id or "").strip() or None

        if not normalized_workspace_id:
            raise IngestionPlanningError(
                code="WORKSPACE_ID_REQUIRED",
                message="workspace_id is required",
                status_code=422,
            )
        if not normalized_job_id:
            raise IngestionPlanningError(
                code="JOB_ID_REQUIRED",
                message="job_id is required",
                status_code=422,
            )
        if not normalized_requested_by:
            raise IngestionPlanningError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )

        with self._connect() as conn:
            job = self._load_job_context(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
            )
            route = select_agent_route(
                message=message,
                has_files=True,
                ingestion_job_status=str(job["status"]),
            )
            logger.info(
                "ingestion_plan_started workspace_id=%s job_id=%s requested_by=%s conversation_id=%s current_status=%s route=%s",
                normalized_workspace_id,
                normalized_job_id,
                normalized_requested_by,
                normalized_conversation_id or "",
                str(job["status"]),
                route.route,
            )
            self._set_job_status(
                conn=conn,
                job_id=normalized_job_id,
                status="planning",
                business_type_guess=None,
                agent_session_id=normalized_conversation_id,
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="job_status_updated",
                payload={"status": "planning", "trigger": "ingestion_plan"},
            )

            agent_output, tool_trace = self._run_planning_agent_loop(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
                upload_id=str(job["upload_id"]),
                requested_by=normalized_requested_by,
                conversation_id=normalized_conversation_id,
                message=message,
            )
            agent_guess = agent_output.agent_guess.model_dump(mode="json")
            analysis_audit = {
                "agent_planning": {
                    "engine": "write_ingestion_agent_loop",
                    "runtime_backend": INGESTION_SDK_RUNTIME_BACKEND,
                    "model": get_settings().ai_model.strip(),
                    "human_approval_tool_required": True,
                }
            }
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="business_type_inferred",
                payload={
                    "business_type": agent_guess["business_type"],
                    "confidence": agent_guess["confidence"],
                    "reasoning": agent_guess.get("reasoning", ""),
                    "analysis_audit": analysis_audit["agent_planning"],
                },
            )
            logger.info(
                "ingestion_agent_plan_generated workspace_id=%s job_id=%s status=%s business_type=%s confidence=%s",
                normalized_workspace_id,
                normalized_job_id,
                agent_output.status,
                agent_guess["business_type"],
                agent_guess["confidence"],
            )

            if agent_output.status == "awaiting_catalog_setup":
                self._assert_human_approval_requested(
                    agent_output=agent_output,
                    tool_trace=tool_trace,
                    expected_stage="catalog_setup",
                )
                if agent_output.suggested_catalog_seed is None:
                    raise IngestionPlanningError(
                        code="AGENT_SETUP_SEED_REQUIRED",
                        message="Agent output must include suggested_catalog_seed for catalog setup",
                        status_code=502,
                    )
                setup_payload = {
                    "status": "awaiting_catalog_setup",
                    "workspace_id": normalized_workspace_id,
                    "job_id": normalized_job_id,
                    "agent_guess": agent_guess,
                    "setup_questions": [
                        item.model_dump(mode="json") for item in agent_output.setup_questions
                    ],
                    "suggested_catalog_seed": agent_output.suggested_catalog_seed.model_dump(mode="json"),
                    "human_approval": agent_output.human_approval.model_dump(mode="json"),
                    "route": route.to_payload(),
                    "tool_trace": tool_trace,
                    "analysis_audit": analysis_audit,
                }
                self._set_job_status(
                    conn=conn,
                    job_id=normalized_job_id,
                    status="awaiting_catalog_setup",
                    business_type_guess=agent_guess["business_type"],
                    agent_session_id=normalized_conversation_id,
                )
                self._insert_event(
                    conn=conn,
                    job_id=normalized_job_id,
                    event_type="setup_required",
                    payload={
                        "business_type": agent_guess["business_type"],
                        "confidence": agent_guess["confidence"],
                        "human_approval": agent_output.human_approval.model_dump(mode="json"),
                        "analysis_audit": analysis_audit["agent_planning"],
                    },
                )
                conn.commit()
                logger.info(
                    "ingestion_plan_completed workspace_id=%s job_id=%s status=awaiting_catalog_setup",
                    normalized_workspace_id,
                    normalized_job_id,
                )
                return setup_payload

            self._assert_human_approval_requested(
                agent_output=agent_output,
                tool_trace=tool_trace,
                expected_stage="proposal_approval",
            )
            if agent_output.proposal is None:
                raise IngestionPlanningError(
                    code="AGENT_PROPOSAL_REQUIRED",
                    message="Agent output must include proposal for user approval",
                    status_code=502,
                )
            proposal = self._normalize_agent_proposal(agent_output.proposal)
            proposal_id = self._persist_proposal(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
                proposal=proposal,
            )
            self._set_job_status(
                conn=conn,
                job_id=normalized_job_id,
                status="awaiting_user_approval",
                business_type_guess=proposal.business_type,
                agent_session_id=normalized_conversation_id,
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="proposal_generated",
                payload={
                    "proposal_id": proposal_id,
                    "recommended_action": proposal.recommended_action,
                    "target_table": proposal.target_table,
                    "human_approval": agent_output.human_approval.model_dump(mode="json"),
                },
            )
            conn.commit()
            logger.info(
                "ingestion_plan_completed workspace_id=%s job_id=%s status=awaiting_user_approval proposal_id=%s target_table=%s recommended_action=%s",
                normalized_workspace_id,
                normalized_job_id,
                proposal_id,
                proposal.target_table or "",
                proposal.recommended_action,
            )

            return {
                "status": "awaiting_user_approval",
                "workspace_id": normalized_workspace_id,
                "job_id": normalized_job_id,
                "proposal_id": proposal_id,
                "proposal_json": proposal.model_dump(mode="json"),
                "human_approval": agent_output.human_approval.model_dump(mode="json"),
                "route": route.to_payload(),
                "existing_tables": self._latest_tool_result(tool_trace, "list_existing_tables"),
                "tool_trace": tool_trace,
                "analysis_audit": analysis_audit,
            }

    def confirm_setup(
        self,
        *,
        workspace_id: str,
        job_id: str,
        requested_by: str,
        setup_seed: IngestionCatalogSetupSeed,
        conversation_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = workspace_id.strip()
        normalized_job_id = job_id.strip()
        normalized_requested_by = requested_by.strip()
        normalized_conversation_id = (conversation_id or "").strip() or None

        if not normalized_workspace_id:
            raise IngestionPlanningError(
                code="WORKSPACE_ID_REQUIRED",
                message="workspace_id is required",
                status_code=422,
            )
        if not normalized_job_id:
            raise IngestionPlanningError(
                code="JOB_ID_REQUIRED",
                message="job_id is required",
                status_code=422,
            )
        if not normalized_requested_by:
            raise IngestionPlanningError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )
        if not SAFE_IDENTIFIER_RE.match(setup_seed.table_name):
            raise IngestionPlanningError(
                code="CATALOG_TABLE_NAME_INVALID",
                message="setup.table_name must be a valid SQL identifier",
                status_code=422,
            )

        with self._connect() as conn:
            job = self._load_job_context(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
            )
            current_status = str(job["status"])
            if current_status not in {"uploaded", "planning", "awaiting_catalog_setup"}:
                raise IngestionPlanningError(
                    code="INGESTION_SETUP_NOT_ALLOWED",
                    message=f"Setup cannot be confirmed when job status is {current_status}",
                    status_code=409,
                )

            upload_info = self._tool_inspect_upload(conn=conn, upload_id=str(job["upload_id"]))
            catalog_entry = self._upsert_catalog_entry_from_setup(
                conn=conn,
                workspace_id=normalized_workspace_id,
                requested_by=normalized_requested_by,
                setup_seed=setup_seed,
                upload_info=upload_info,
            )
            self._set_job_status(
                conn=conn,
                job_id=normalized_job_id,
                status="planning",
                business_type_guess=setup_seed.business_type,
                agent_session_id=normalized_conversation_id,
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="setup_confirmed",
                payload={
                    "catalog_entry_id": catalog_entry["id"],
                    "business_type": catalog_entry["business_type"],
                    "table_name": catalog_entry["table_name"],
                },
            )
            conn.commit()

        plan_payload = self.build_plan(
            workspace_id=normalized_workspace_id,
            job_id=normalized_job_id,
            requested_by=normalized_requested_by,
            conversation_id=normalized_conversation_id,
            message=message,
        )
        plan_payload["setup"] = {
            "status": "confirmed",
            "catalog_entry": catalog_entry,
        }
        return plan_payload

    def approve_plan(
        self,
        *,
        workspace_id: str,
        job_id: str,
        proposal_id: str,
        approved_action: str,
        approved_by: str,
        user_overrides: IngestionApprovalOverrides | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = workspace_id.strip()
        normalized_job_id = job_id.strip()
        normalized_proposal_id = proposal_id.strip()
        normalized_approved_by = approved_by.strip()
        normalized_action = approved_action.strip().lower()

        if not normalized_workspace_id:
            raise IngestionPlanningError(
                code="WORKSPACE_ID_REQUIRED",
                message="workspace_id is required",
                status_code=422,
            )
        if not normalized_job_id:
            raise IngestionPlanningError(
                code="JOB_ID_REQUIRED",
                message="job_id is required",
                status_code=422,
            )
        if not normalized_proposal_id:
            raise IngestionPlanningError(
                code="PROPOSAL_ID_REQUIRED",
                message="proposal_id is required",
                status_code=422,
            )
        if not normalized_approved_by:
            raise IngestionPlanningError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )
        if normalized_action not in DEFAULT_ACTION_OPTIONS:
            raise IngestionPlanningError(
                code="APPROVED_ACTION_INVALID",
                message="approved_action is not supported",
                status_code=422,
            )

        with self._connect() as conn:
            self._ensure_user_record(conn=conn, user_id=normalized_approved_by)
            job = self._load_job_for_approval(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
            )
            proposal_row, proposal_payload = self._load_proposal(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
                proposal_id=normalized_proposal_id,
            )
            if normalized_action not in proposal_payload.candidate_actions:
                raise IngestionPlanningError(
                    code="APPROVED_ACTION_NOT_IN_CANDIDATES",
                    message="approved_action is not in proposal candidate_actions",
                    status_code=422,
                )

            if normalized_action == "cancel":
                self._set_job_status(
                    conn=conn,
                    job_id=normalized_job_id,
                    status="cancelled",
                    business_type_guess=proposal_payload.business_type,
                    agent_session_id=str(job["agent_session_id"]) if job["agent_session_id"] else None,
                )
                self._insert_event(
                    conn=conn,
                    job_id=normalized_job_id,
                    event_type="proposal_cancelled",
                    payload={
                        "proposal_id": normalized_proposal_id,
                        "approved_by": normalized_approved_by,
                    },
                )
                conn.commit()
                return {
                    "status": "cancelled",
                    "workspace_id": normalized_workspace_id,
                    "job_id": normalized_job_id,
                    "proposal_id": normalized_proposal_id,
                    "approved_action": "cancel",
                }

            overrides_payload = (user_overrides.model_dump(mode="json") if user_overrides else {})
            target_table, time_grain = self._resolve_approved_target(
                proposal_payload=proposal_payload,
                approved_action=normalized_action,
                overrides=user_overrides,
            )
            staging_table = self._staging_table_name(normalized_job_id)
            finalized_sql = self._build_validated_sql(
                approved_action=normalized_action,
                target_table=target_table,
                staging_table=staging_table,
                proposal_payload=proposal_payload,
            )
            validator = SQLWriteValidator(
                target_table=target_table,
                staging_table=staging_table,
                action_mode=normalized_action,
            )
            validated_sql = validator.validate(finalized_sql)
            sql_hash = hashlib.sha256(validated_sql.encode("utf-8")).hexdigest()
            dry_run_summary = self._build_dry_run_summary(
                proposal_payload=proposal_payload,
                approved_action=normalized_action,
                target_table=target_table,
                time_grain=time_grain,
            )

            self._set_job_status(
                conn=conn,
                job_id=normalized_job_id,
                status="approved",
                business_type_guess=proposal_payload.business_type,
                agent_session_id=str(job["agent_session_id"]) if job["agent_session_id"] else None,
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="proposal_approved",
                payload={
                    "proposal_id": normalized_proposal_id,
                    "approved_action": normalized_action,
                    "approved_by": normalized_approved_by,
                    "target_table": target_table,
                    "time_grain": time_grain,
                    "validated_sql": validated_sql,
                    "validated_sql_hash": sql_hash,
                    "dry_run_summary": dry_run_summary,
                    "user_overrides": overrides_payload,
                    "proposal_version": int(proposal_row["proposal_version"]),
                },
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="job_status_updated",
                payload={"status": "approved", "trigger": "ingestion_approve"},
            )
            conn.commit()

        return {
            "status": "approved",
            "workspace_id": normalized_workspace_id,
            "job_id": normalized_job_id,
            "proposal_id": normalized_proposal_id,
            "approved_action": normalized_action,
            "target_table": target_table,
            "time_grain": time_grain,
            "dry_run_summary": dry_run_summary,
        }

    def execute_plan(
        self,
        *,
        workspace_id: str,
        job_id: str,
        proposal_id: str,
        executed_by: str,
    ) -> dict[str, Any]:
        normalized_workspace_id = workspace_id.strip()
        normalized_job_id = job_id.strip()
        normalized_proposal_id = proposal_id.strip()
        normalized_executed_by = executed_by.strip()

        if not normalized_workspace_id:
            raise IngestionPlanningError(
                code="WORKSPACE_ID_REQUIRED",
                message="workspace_id is required",
                status_code=422,
            )
        if not normalized_job_id:
            raise IngestionPlanningError(
                code="JOB_ID_REQUIRED",
                message="job_id is required",
                status_code=422,
            )
        if not normalized_proposal_id:
            raise IngestionPlanningError(
                code="PROPOSAL_ID_REQUIRED",
                message="proposal_id is required",
                status_code=422,
            )
        if not normalized_executed_by:
            raise IngestionPlanningError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )

        started_at = _utc_now()
        with self._connect() as conn:
            self._ensure_user_record(conn=conn, user_id=normalized_executed_by)
            job = self._load_job_for_execution(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
            )
            _proposal_row, proposal_payload = self._load_proposal(
                conn=conn,
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
                proposal_id=normalized_proposal_id,
            )
            approval_event = self._load_latest_approval_event(
                conn=conn,
                job_id=normalized_job_id,
                proposal_id=normalized_proposal_id,
            )
            validated_sql = str(approval_event["validated_sql"])
            approved_action = str(approval_event["approved_action"])
            target_table = str(approval_event["target_table"])
            dry_run_summary = approval_event["dry_run_summary"]
            validator = SQLWriteValidator(
                target_table=target_table,
                staging_table=self._staging_table_name(normalized_job_id),
                action_mode=approved_action,
            )
            validated_sql = validator.validate(validated_sql)
            expected_sql_hash = str(approval_event["validated_sql_hash"])
            actual_sql_hash = hashlib.sha256(validated_sql.encode("utf-8")).hexdigest()
            if expected_sql_hash != actual_sql_hash:
                raise IngestionPlanningError(
                    code="APPROVAL_SQL_HASH_MISMATCH",
                    message="Approved SQL binding is invalid",
                    status_code=409,
                )

            upload_info = self._tool_inspect_upload(conn=conn, upload_id=str(job["upload_id"]))
            self._set_job_status(
                conn=conn,
                job_id=normalized_job_id,
                status="executing",
                business_type_guess=proposal_payload.business_type,
                agent_session_id=str(job["agent_session_id"]) if job["agent_session_id"] else None,
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="job_status_updated",
                payload={"status": "executing", "trigger": "ingestion_execute"},
            )
            conn.commit()

        execution_id = uuid.uuid4().hex
        execution_mode = approved_action
        try:
            receipt = self._run_execution_transaction(
                workspace_id=normalized_workspace_id,
                job_id=normalized_job_id,
                target_table=target_table,
                approved_action=approved_action,
                validated_sql=validated_sql,
                dry_run_summary=dry_run_summary,
                upload_info=upload_info,
                proposal_payload=proposal_payload,
            )
            execution_status = "succeeded"
            failure_message = ""
        except IngestionPlanningError as exc:
            execution_status = "failed"
            failure_message = exc.message
            receipt = {
                "success": False,
                "workspace_id": normalized_workspace_id,
                "job_id": normalized_job_id,
                "target_table": target_table,
                "approved_action": approved_action,
                "error": {"code": exc.code, "message": exc.message},
            }
        except Exception as exc:  # pragma: no cover - defensive path
            execution_status = "failed"
            failure_message = str(exc)
            receipt = {
                "success": False,
                "workspace_id": normalized_workspace_id,
                "job_id": normalized_job_id,
                "target_table": target_table,
                "approved_action": approved_action,
                "error": {"code": "INGESTION_EXECUTION_FAILED", "message": str(exc)},
            }

        finished_at = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_executions (
                    id,
                    job_id,
                    proposal_id,
                    workspace_id,
                    executed_by,
                    execution_mode,
                    validated_sql,
                    dry_run_summary,
                    execution_receipt,
                    status,
                    started_at,
                    finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    normalized_job_id,
                    normalized_proposal_id,
                    normalized_workspace_id,
                    normalized_executed_by,
                    execution_mode,
                    validated_sql,
                    json.dumps(dry_run_summary, ensure_ascii=False),
                    json.dumps(receipt, ensure_ascii=False),
                    execution_status,
                    started_at,
                    finished_at,
                ),
            )
            final_job_status = "succeeded" if execution_status == "succeeded" else "failed"
            self._set_job_status(
                conn=conn,
                job_id=normalized_job_id,
                status=final_job_status,
                business_type_guess=None,
                agent_session_id=None,
            )
            event_type = "execution_succeeded" if execution_status == "succeeded" else "execution_failed"
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type=event_type,
                payload={
                    "execution_id": execution_id,
                    "proposal_id": normalized_proposal_id,
                    "status": execution_status,
                    "receipt": receipt,
                },
            )
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="job_status_updated",
                payload={"status": final_job_status, "trigger": "ingestion_execute_finalize"},
            )
            conn.commit()

        if execution_status != "succeeded":
            raise IngestionPlanningError(
                code="INGESTION_EXECUTION_FAILED",
                message=f"Execution failed: {failure_message}",
                status_code=500,
            )

        return {
            "status": "succeeded",
            "workspace_id": normalized_workspace_id,
            "job_id": normalized_job_id,
            "proposal_id": normalized_proposal_id,
            "execution_id": execution_id,
            "receipt": receipt,
        }

    def _run_planning_agent_loop(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
        upload_id: str,
        requested_by: str,
        conversation_id: str | None,
        message: str | None,
    ) -> tuple[IngestionAgentPlanOutput, list[dict[str, Any]]]:
        settings = get_settings()
        auth_token_source = settings.anthropic_auth_token or settings.ai_api_key
        if not auth_token_source.strip() or not settings.ai_model.strip():
            raise IngestionPlanningError(
                code="INGESTION_AI_NOT_CONFIGURED",
                message="Claude Agent SDK credentials are not configured for ingestion planning",
                status_code=503,
            )

        tool_trace_snapshot: list[dict[str, Any]] = []

        async def runner() -> tuple[IngestionAgentPlanOutput, list[dict[str, Any]]]:
            return await self._run_planning_agent_loop_async(
                conn=conn,
                workspace_id=workspace_id,
                job_id=job_id,
                upload_id=upload_id,
                requested_by=requested_by,
                conversation_id=conversation_id,
                message=message,
                tool_trace_sink=tool_trace_snapshot,
            )

        try:
            return anyio.run(runner)
        except IngestionPlanningError:
            raise
        except TimeoutError as exc:
            recovered = self._recover_agent_output_from_tool_trace(tool_trace=tool_trace_snapshot)
            if recovered is not None:
                logger.warning(
                    "ingestion_agent_output_recovered_from_tool_trace job_id=%s reason=timeout_outer",
                    job_id,
                )
                return recovered, tool_trace_snapshot
            raise IngestionPlanningError(
                code="INGESTION_AI_UNAVAILABLE",
                message=(
                    "Claude Agent SDK timed out during ingestion planning "
                    f"(>{settings.agent_timeout_seconds}s)"
                ),
                status_code=503,
            ) from exc
        except ClaudeSDKError as exc:
            recovered = self._recover_agent_output_from_tool_trace(tool_trace=tool_trace_snapshot)
            if recovered is not None:
                logger.warning(
                    "ingestion_agent_output_recovered_from_tool_trace job_id=%s reason=claude_sdk_error",
                    job_id,
                )
                return recovered, tool_trace_snapshot
            suffix = str(exc).strip()
            detail = f": {suffix}" if suffix else ""
            raise IngestionPlanningError(
                code="INGESTION_AI_UNAVAILABLE",
                message=f"Claude Agent SDK is unavailable for ingestion planning{detail}",
                status_code=503,
            ) from exc
        except Exception as exc:
            raise IngestionPlanningError(
                code="INGESTION_AI_UNAVAILABLE",
                message=f"Claude Agent SDK failed during ingestion planning: {exc}",
                status_code=503,
            ) from exc

    async def _run_planning_agent_loop_async(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
        upload_id: str,
        requested_by: str,
        conversation_id: str | None,
        message: str | None,
        tool_trace_sink: list[dict[str, Any]] | None = None,
    ) -> tuple[IngestionAgentPlanOutput, list[dict[str, Any]]]:
        settings = get_settings()
        tool_trace = tool_trace_sink if tool_trace_sink is not None else []
        options = self._build_ingestion_sdk_options(
            conn=conn,
            job_id=job_id,
            tool_trace=tool_trace,
        )
        prompt = self._build_ingestion_agent_prompt(
            workspace_id=workspace_id,
            job_id=job_id,
            upload_id=upload_id,
            requested_by=requested_by,
            message=message,
        )
        raw_output: dict[str, Any] | None = None
        text_blocks: list[str] = []
        session_id = conversation_id or f"ingestion-{job_id}"

        try:
            with anyio.fail_after(settings.agent_timeout_seconds):
                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt, session_id=session_id)
                    async for sdk_message in client.receive_response():
                        candidate = self._consume_ingestion_sdk_message(
                            message=sdk_message,
                            text_blocks=text_blocks,
                        )
                        if candidate is not None:
                            raw_output = candidate
        except TimeoutError:
            recovered = self._recover_agent_output_from_tool_trace(tool_trace=tool_trace)
            if recovered is not None:
                logger.warning(
                    "ingestion_agent_output_recovered_from_tool_trace job_id=%s reason=timeout",
                    job_id,
                )
                return recovered, tool_trace
            raise

        if raw_output is None and text_blocks:
            raw_output = _decode_json_dict("\n".join(text_blocks))
        if raw_output is None:
            recovered = self._recover_agent_output_from_tool_trace(tool_trace=tool_trace)
            if recovered is not None:
                logger.warning(
                    "ingestion_agent_output_recovered_from_tool_trace job_id=%s reason=missing_structured_output",
                    job_id,
                )
                return recovered, tool_trace
            raise IngestionPlanningError(
                code="AGENT_STRUCTURED_OUTPUT_MISSING",
                message="Write Ingestion Agent did not return structured output",
                status_code=502,
            )
        try:
            output = IngestionAgentPlanOutput.model_validate(raw_output)
        except Exception as exc:
            recovered = self._recover_agent_output_from_tool_trace(tool_trace=tool_trace)
            if recovered is not None:
                logger.warning(
                    "ingestion_agent_output_recovered_from_tool_trace job_id=%s reason=invalid_structured_output",
                    job_id,
                )
                return recovered, tool_trace
            raise IngestionPlanningError(
                code="AGENT_STRUCTURED_OUTPUT_INVALID",
                message="Write Ingestion Agent returned invalid structured output",
                status_code=502,
            ) from exc
        return output, tool_trace

    def _build_ingestion_sdk_options(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        tool_trace: list[dict[str, Any]],
    ) -> ClaudeAgentOptions:
        settings = get_settings()

        async def can_use_tool(
            tool_name: str,
            input_data: dict[str, Any],
            permission_context: Any,
        ) -> PermissionResultAllow | PermissionResultDeny:
            _ = (input_data, permission_context)
            canonical_name = _canonical_ingestion_tool_name(tool_name)
            if canonical_name in INGESTION_SDK_TOOL_NAMES:
                return PermissionResultAllow()
            return PermissionResultDeny(
                message=f"Tool '{tool_name}' is outside the Write Ingestion Agent tool surface."
            )

        server = create_sdk_mcp_server(
            name=INGESTION_SDK_MCP_SERVER_NAME,
            version="1.0.0",
            tools=self._build_ingestion_sdk_tools(
                conn=conn,
                job_id=job_id,
                tool_trace=tool_trace,
            ),
        )
        env: dict[str, str] = {
            "API_TIMEOUT_MS": str(settings.api_timeout_ms),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }
        auth_token_source = settings.anthropic_auth_token or settings.ai_api_key
        auth_token = auth_token_source.strip()
        if auth_token:
            env["ANTHROPIC_API_KEY"] = auth_token
            env["ANTHROPIC_AUTH_TOKEN"] = auth_token
        if settings.anthropic_base_url.strip():
            env["ANTHROPIC_BASE_URL"] = settings.anthropic_base_url.strip()
        model = settings.ai_model.strip() or None
        if model:
            env["ANTHROPIC_MODEL"] = model
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = (
                settings.anthropic_default_haiku_model.strip() or model
            )

        return ClaudeAgentOptions(
            tools=[],
            system_prompt=INGESTION_AGENT_SYSTEM_PROMPT,
            mcp_servers={INGESTION_SDK_MCP_SERVER_NAME: server},
            can_use_tool=can_use_tool,
            permission_mode="default",
            max_turns=max(settings.agent_max_tool_steps, MIN_INGESTION_AGENT_MAX_TURNS),
            model=model,
            cwd=str(Path.cwd()),
            env=env,
            output_format={
                "type": "json_schema",
                "schema": IngestionAgentPlanOutput.model_json_schema(),
            },
        )

    def _build_ingestion_sdk_tools(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        tool_trace: list[dict[str, Any]],
    ) -> list[Any]:
        sdk_tools: list[Any] = []
        for definition in INGESTION_AGENT_TOOL_DEFINITIONS:
            tool_name = str(definition["name"])
            description = str(definition["description"])
            input_schema = definition["parameters"]
            is_read_only = bool(definition.get("read_only", True))
            annotations = ToolAnnotations(
                readOnlyHint=is_read_only,
                destructiveHint=False,
                idempotentHint=is_read_only,
                openWorldHint=False,
            )

            async def handler(args: dict[str, Any], _tool_name: str = tool_name) -> dict[str, Any]:
                result = self._invoke_ingestion_sdk_tool(
                    conn=conn,
                    job_id=job_id,
                    tool_trace=tool_trace,
                    tool_name=_tool_name,
                    arguments=args,
                )
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    ],
                    "is_error": False,
                }

            sdk_tools.append(
                tool(
                    tool_name,
                    description,
                    input_schema,
                    annotations=annotations,
                )(handler)
            )
        return sdk_tools

    def _invoke_ingestion_sdk_tool(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        tool_trace: list[dict[str, Any]],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        canonical_name = _canonical_ingestion_tool_name(tool_name)
        if canonical_name not in INGESTION_SDK_TOOL_NAMES:
            raise IngestionPlanningError(
                code="INGESTION_TOOL_NOT_ALLOWED",
                message=f"Tool '{tool_name}' is outside the Write Ingestion Agent tool surface",
                status_code=403,
            )
        if not isinstance(arguments, dict):
            arguments = {}
        return self._run_tool(
            conn=conn,
            job_id=job_id,
            trace=tool_trace,
            name=canonical_name,
            arguments=arguments,
            handler=lambda: self._handle_ingestion_tool(
                conn=conn,
                job_id=job_id,
                tool_name=canonical_name,
                arguments=arguments,
            ),
        )

    def _handle_ingestion_tool(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "get_workspace_catalog":
            return self._tool_get_workspace_catalog(
                conn=conn,
                workspace_id=str(arguments.get("workspace_id", "")),
            )
        if tool_name == "list_existing_tables":
            return self._tool_list_existing_tables(
                conn=conn,
                workspace_id=str(arguments.get("workspace_id", "")),
            )
        if tool_name == "inspect_upload":
            return self._tool_inspect_upload(
                conn=conn,
                upload_id=str(arguments.get("upload_id", "")),
            )
        if tool_name == "describe_table_schema":
            return self._tool_describe_table_schema_by_name(
                conn=conn,
                workspace_id=str(arguments.get("workspace_id", "")),
                table_name=str(arguments.get("table_name", "")),
            )
        if tool_name == "build_diff_preview":
            upload_info = self._tool_inspect_upload(
                conn=conn,
                upload_id=str(arguments.get("upload_id", "")),
            )
            return self._tool_build_diff_preview(
                upload_info=upload_info,
                match_columns=[
                    str(item).strip().lower()
                    for item in arguments.get("match_columns", [])
                    if str(item).strip()
                ],
                action_mode=str(arguments.get("action_mode", "")),
            )
        if tool_name == "generate_write_sql_draft":
            return self._tool_generate_write_sql_draft(
                workspace_id=str(arguments.get("workspace_id", "")),
                job_id=str(arguments.get("job_id", job_id)),
                target_table=str(arguments.get("target_table", "")),
                action_mode=str(arguments.get("action_mode", "")),
                match_columns=[
                    str(item).strip().lower()
                    for item in arguments.get("match_columns", [])
                    if str(item).strip()
                ],
            )
        if tool_name in INGESTION_APPROVAL_TOOL_ALIASES:
            return self._tool_request_human_approval(conn=conn, job_id=job_id, arguments=arguments)
        raise IngestionPlanningError(
            code="INGESTION_TOOL_NOT_ALLOWED",
            message=f"Unsupported ingestion tool: {tool_name}",
            status_code=403,
        )

    @staticmethod
    def _build_ingestion_agent_prompt(
        *,
        workspace_id: str,
        job_id: str,
        upload_id: str,
        requested_by: str,
        message: str | None,
    ) -> str:
        return json.dumps(
            {
                "task": "Build the next write ingestion lifecycle output.",
                "workspace_id": workspace_id,
                "job_id": job_id,
                "upload_id": upload_id,
                "requested_by": requested_by,
                "user_message": message or "",
                "required_tool_sequence": [
                    "inspect_upload",
                    "get_workspace_catalog",
                    "list_existing_tables",
                    "describe_table_schema when a target table is considered",
                    "build_diff_preview when producing a proposal",
                    "generate_write_sql_draft when producing a proposal",
                    f"{INGESTION_APPROVAL_TOOL_NAME} before the final structured output",
                ],
                "available_approval_options": {
                    "catalog_setup": CATALOG_SETUP_APPROVAL_OPTIONS,
                    "proposal_approval": DEFAULT_ACTION_OPTIONS,
                },
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _consume_ingestion_sdk_message(
        *,
        message: Any,
        text_blocks: list[str],
    ) -> dict[str, Any] | None:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    text_blocks.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    continue
            return None
        if isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    continue
            return None
        if isinstance(message, ResultMessage):
            if message.is_error:
                error_suffix = ""
                if message.errors:
                    error_suffix = f": {'; '.join(str(item) for item in message.errors)}"
                raise IngestionPlanningError(
                    code="INGESTION_AI_UNAVAILABLE",
                    message=(
                        "Write Ingestion Agent ended before producing structured output "
                        f"({message.subtype}, turns={message.num_turns}){error_suffix}"
                    ),
                    status_code=503,
                )
            if isinstance(message.structured_output, dict):
                return message.structured_output
            if message.result:
                return _decode_json_dict(message.result)
        return None

    def _assert_human_approval_requested(
        self,
        *,
        agent_output: IngestionAgentPlanOutput,
        tool_trace: list[dict[str, Any]],
        expected_stage: str,
    ) -> None:
        approval = agent_output.human_approval
        if not approval.required or approval.stage != expected_stage:
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_REQUIRED",
                message="Agent output must require human approval for the next step",
                status_code=502,
            )
        allowed_options = (
            CATALOG_SETUP_APPROVAL_OPTIONS
            if expected_stage == "catalog_setup"
            else DEFAULT_ACTION_OPTIONS
        )
        if not approval.options or any(option not in allowed_options for option in approval.options):
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_OPTIONS_INVALID",
                message="Agent human approval options are outside the designed choices",
                status_code=502,
            )
        if approval.recommended_option and approval.recommended_option not in approval.options:
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_RECOMMENDATION_INVALID",
                message="Agent human approval recommendation is not in approval options",
                status_code=502,
            )
        for item in tool_trace:
            if item.get("tool_name") not in INGESTION_APPROVAL_TOOL_ALIASES:
                continue
            arguments = item.get("arguments")
            if isinstance(arguments, dict) and arguments.get("stage") == expected_stage:
                return
        raise IngestionPlanningError(
            code="HUMAN_APPROVAL_NOT_REQUESTED",
            message=(
                "Agent must call AskUserQuestion before returning the next step "
                "(request_human_approval is accepted as a legacy alias)"
            ),
            status_code=502,
        )

    @staticmethod
    def _normalize_agent_proposal(proposal: IngestionProposalPayload) -> IngestionProposalPayload:
        candidate_actions = list(proposal.candidate_actions)
        if any(action not in DEFAULT_ACTION_OPTIONS for action in candidate_actions):
            raise IngestionPlanningError(
                code="AGENT_PROPOSAL_ACTION_INVALID",
                message="Agent proposal contains an unsupported candidate action",
                status_code=502,
            )
        if proposal.recommended_action not in candidate_actions:
            raise IngestionPlanningError(
                code="AGENT_PROPOSAL_RECOMMENDATION_INVALID",
                message="Agent recommended action must be present in candidate_actions",
                status_code=502,
            )
        if "cancel" not in candidate_actions:
            raise IngestionPlanningError(
                code="AGENT_PROPOSAL_CANCEL_REQUIRED",
                message="Agent proposal candidate_actions must include cancel",
                status_code=502,
            )
        return proposal

    @staticmethod
    def _latest_tool_result(tool_trace: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
        for item in reversed(tool_trace):
            if item.get("tool_name") == tool_name and isinstance(item.get("result"), dict):
                return item["result"]
        return {}

    @staticmethod
    def _latest_tool_trace_item(
        tool_trace: list[dict[str, Any]],
        *,
        names: set[str] | frozenset[str] | tuple[str, ...] | list[str],
    ) -> dict[str, Any] | None:
        name_set = set(names)
        for item in reversed(tool_trace):
            if item.get("tool_name") in name_set:
                return item
        return None

    def _recover_agent_output_from_tool_trace(
        self,
        *,
        tool_trace: list[dict[str, Any]],
    ) -> IngestionAgentPlanOutput | None:
        approval_item = self._latest_tool_trace_item(
            tool_trace,
            names=INGESTION_APPROVAL_TOOL_ALIASES,
        )
        if approval_item is None:
            return None

        arguments = approval_item.get("arguments") if isinstance(approval_item.get("arguments"), dict) else {}
        result = approval_item.get("result") if isinstance(approval_item.get("result"), dict) else {}
        stage = str(result.get("stage") or arguments.get("stage") or "").strip()
        if stage not in {"catalog_setup", "proposal_approval"}:
            return None

        if stage == "catalog_setup":
            allowed_options = list(CATALOG_SETUP_APPROVAL_OPTIONS)
            default_recommended = "confirm_catalog_setup"
            default_mechanism = "catalog_setup_card"
        else:
            allowed_options = list(DEFAULT_ACTION_OPTIONS)
            default_recommended = "update_existing"
            default_mechanism = "frontend_approval_card"

        raw_options = result.get("options") if isinstance(result.get("options"), list) else arguments.get("options")
        options = [
            str(item).strip()
            for item in (raw_options or [])
            if str(item).strip() in allowed_options
        ]
        if not options:
            options = list(allowed_options)

        recommended_option = str(
            result.get("recommended_option") or arguments.get("recommended_option") or ""
        ).strip()
        if recommended_option not in options:
            recommended_option = default_recommended if default_recommended in options else options[0]

        question = str(result.get("question") or arguments.get("question") or "").strip()
        if not question:
            question = (
                "Please confirm the catalog setup before proceeding."
                if stage == "catalog_setup"
                else "Please choose the ingestion action."
            )
        if len(question) > 300:
            question = question[:300].rstrip()

        mechanism = str(result.get("mechanism") or "").strip() or default_mechanism
        human_approval_payload = {
            "required": True,
            "mechanism": mechanism,
            "stage": stage,
            "question": question,
            "options": options,
            "recommended_option": recommended_option,
        }

        schema = self._latest_tool_result(tool_trace, "describe_table_schema")
        upload_info = self._latest_tool_result(tool_trace, "inspect_upload")
        column_summary = upload_info.get("column_summary") if isinstance(upload_info.get("column_summary"), dict) else {}
        raw_columns = column_summary.get("all_columns") if isinstance(column_summary.get("all_columns"), list) else []
        upload_columns = [str(item).strip() for item in raw_columns if str(item).strip()]
        normalized_columns: list[str] = []
        for raw_column in upload_columns:
            candidate = self._normalize_identifier(raw_column)
            if candidate and candidate not in normalized_columns:
                normalized_columns.append(candidate)

        business_type = str(schema.get("business_type") or "other").strip()
        if business_type not in {"roster", "project_progress", "attendance", "other"}:
            business_type = "other"
        agent_guess_payload = {
            "business_type": business_type,
            "confidence": 0.55,
            "reasoning": (
                "Recovered from tool trace because the agent called AskUserQuestion "
                "but did not return structured output before timeout."
            ),
        }

        if stage == "catalog_setup":
            table_name = str(schema.get("table_name") or "employee_roster").strip().lower()
            if not SAFE_IDENTIFIER_RE.match(table_name):
                table_name = self._normalize_identifier(table_name) or "employee_roster"

            match_columns = [
                str(item).strip().lower()
                for item in (schema.get("match_columns") if isinstance(schema.get("match_columns"), list) else [])
                if str(item).strip()
            ]
            if not match_columns and normalized_columns:
                match_columns = [normalized_columns[0]]

            primary_keys = [
                str(item).strip().lower()
                for item in (schema.get("primary_keys") if isinstance(schema.get("primary_keys"), list) else [])
                if str(item).strip()
            ]
            if not primary_keys:
                primary_keys = list(match_columns)

            write_mode = str(schema.get("write_mode") or "update_existing").strip()
            if write_mode not in {"update_existing", "time_partitioned_new_table", "new_table"}:
                write_mode = "update_existing"
            time_grain = str(schema.get("time_grain") or "none").strip()
            if time_grain not in {"none", "month", "quarter", "year"}:
                time_grain = "none"

            setup_questions = [
                {
                    "question_id": "business_type",
                    "title": "Select business type",
                    "options": ["roster", "project_progress", "attendance", "other"],
                },
                {
                    "question_id": "write_mode",
                    "title": "Select write mode",
                    "options": ["update_existing", "time_partitioned_new_table", "new_table"],
                },
                {
                    "question_id": "match_columns",
                    "title": "Select match columns",
                    "options": upload_columns[:12],
                },
            ]
            try:
                return IngestionAgentPlanOutput.model_validate(
                    {
                        "status": "awaiting_catalog_setup",
                        "agent_guess": agent_guess_payload,
                        "setup_questions": setup_questions,
                        "suggested_catalog_seed": {
                            "business_type": business_type,
                            "table_name": table_name,
                            "human_label": table_name.replace("_", " ").title(),
                            "write_mode": write_mode,
                            "time_grain": time_grain,
                            "primary_keys": primary_keys,
                            "match_columns": match_columns,
                            "is_active_target": True,
                            "description": (
                                "Recovered from AskUserQuestion fallback after SDK timeout."
                            ),
                        },
                        "human_approval": human_approval_payload,
                    }
                )
            except Exception:
                return None

        diff_preview_result = self._latest_tool_result(tool_trace, "build_diff_preview")
        draft_trace = self._latest_tool_trace_item(
            tool_trace,
            names={"generate_write_sql_draft"},
        )
        draft_arguments = draft_trace.get("arguments") if isinstance(draft_trace, dict) else {}
        sql_payload = self._latest_tool_result(tool_trace, "generate_write_sql_draft")

        target_table = str(draft_arguments.get("target_table") or schema.get("table_name") or "").strip().lower()
        if target_table and not SAFE_IDENTIFIER_RE.match(target_table):
            target_table = self._normalize_identifier(target_table)
        if not target_table:
            target_table = None

        candidate_actions = [item for item in options if item in DEFAULT_ACTION_OPTIONS]
        if "cancel" not in candidate_actions:
            candidate_actions.append("cancel")
        recommended_action = recommended_option if recommended_option in candidate_actions else candidate_actions[0]

        match_columns: list[str] = []
        for item in (
            draft_arguments.get("match_columns")
            if isinstance(draft_arguments.get("match_columns"), list)
            else []
        ):
            normalized = self._normalize_identifier(str(item))
            if normalized and normalized not in match_columns:
                match_columns.append(normalized)
        if not match_columns:
            for item in (
                schema.get("match_columns")
                if isinstance(schema.get("match_columns"), list)
                else []
            ):
                normalized = self._normalize_identifier(str(item))
                if normalized and normalized not in match_columns:
                    match_columns.append(normalized)
        if not match_columns and normalized_columns:
            match_columns = [normalized_columns[0]]

        time_grain = str(schema.get("time_grain") or "none").strip()
        if time_grain not in {"none", "month", "quarter", "year"}:
            time_grain = "none"

        def _as_non_negative_int(value: Any) -> int:
            try:
                return max(int(value), 0)
            except (TypeError, ValueError):
                return 0

        column_mapping: dict[str, str] = {}
        for raw_column in upload_columns:
            normalized = self._normalize_identifier(raw_column)
            if not normalized:
                continue
            column_mapping[raw_column] = normalized

        proposal_payload = {
            "business_type": business_type,
            "confidence": 0.6,
            "recommended_action": recommended_action,
            "candidate_actions": candidate_actions,
            "target_table": target_table,
            "time_grain": time_grain,
            "match_columns": match_columns,
            "column_mapping": column_mapping,
            "diff_preview": {
                "predicted_insert_count": _as_non_negative_int(
                    diff_preview_result.get("predicted_insert_count")
                ),
                "predicted_update_count": _as_non_negative_int(
                    diff_preview_result.get("predicted_update_count")
                ),
                "predicted_conflict_count": _as_non_negative_int(
                    diff_preview_result.get("predicted_conflict_count")
                ),
            },
            "risks": [
                "Recovered from AskUserQuestion fallback after SDK timeout; review before approval."
            ],
            "explanation": (
                "Recovered a proposal from tool trace because the agent did not return "
                "structured output before timeout."
            ),
            "sql_draft": str(sql_payload.get("sql_draft") or "").strip(),
            "requires_catalog_setup": False,
        }
        try:
            return IngestionAgentPlanOutput.model_validate(
                {
                    "status": "awaiting_user_approval",
                    "agent_guess": agent_guess_payload,
                    "proposal": proposal_payload,
                    "human_approval": human_approval_payload,
                }
            )
        except Exception:
            return None

    def _run_tool(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        trace: list[dict[str, Any]],
        name: str,
        arguments: dict[str, Any],
        handler: Any,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        self._insert_event(
            conn=conn,
            job_id=job_id,
            event_type="tool_use",
            payload={"tool_name": name, "arguments": arguments},
        )
        logger.info("ingestion_tool_use job_id=%s tool_name=%s arguments=%s", job_id, name, _compact_json(arguments))
        try:
            result = handler()
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            error_payload = {
                "tool_name": name,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_ms": elapsed_ms,
            }
            self._insert_event(
                conn=conn,
                job_id=job_id,
                event_type="tool_error",
                payload=error_payload,
            )
            trace.append({"tool_name": name, "arguments": arguments, "error": error_payload})
            logger.warning(
                "ingestion_tool_error job_id=%s tool_name=%s elapsed_ms=%s error_type=%s error=%s",
                job_id,
                name,
                elapsed_ms,
                type(exc).__name__,
                str(exc),
            )
            raise

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        self._insert_event(
            conn=conn,
            job_id=job_id,
            event_type="tool_result",
            payload={"tool_name": name, "result": result, "elapsed_ms": elapsed_ms},
        )
        trace.append(
            {
                "tool_name": name,
                "arguments": arguments,
                "result": result,
                "elapsed_ms": elapsed_ms,
            }
        )
        logger.info(
            "ingestion_tool_result job_id=%s tool_name=%s elapsed_ms=%s",
            job_id,
            name,
            elapsed_ms,
        )
        return result

    def _load_job_for_approval(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT id, workspace_id, upload_id, status, agent_session_id
            FROM ingestion_jobs
            WHERE id = ? AND workspace_id = ?
            """,
            (job_id, workspace_id),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="INGESTION_JOB_NOT_FOUND",
                message="Ingestion job not found",
                status_code=404,
            )
        status = str(row["status"])
        if status != "awaiting_user_approval":
            raise IngestionPlanningError(
                code="INGESTION_APPROVAL_NOT_ALLOWED",
                message=f"Job status does not allow approval: {status}",
                status_code=409,
            )
        return row

    def _load_job_for_execution(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT id, workspace_id, upload_id, status, agent_session_id
            FROM ingestion_jobs
            WHERE id = ? AND workspace_id = ?
            """,
            (job_id, workspace_id),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="INGESTION_JOB_NOT_FOUND",
                message="Ingestion job not found",
                status_code=404,
            )
        status = str(row["status"])
        if status != "approved":
            raise IngestionPlanningError(
                code="INGESTION_EXECUTION_NOT_ALLOWED",
                message=f"Job status does not allow execution: {status}",
                status_code=409,
            )
        return row

    def _load_proposal(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
        proposal_id: str,
    ) -> tuple[sqlite3.Row, IngestionProposalPayload]:
        row = conn.execute(
            """
            SELECT id, workspace_id, job_id, proposal_version, proposal_json
            FROM ingestion_proposals
            WHERE id = ? AND workspace_id = ? AND job_id = ?
            """,
            (proposal_id, workspace_id, job_id),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="INGESTION_PROPOSAL_NOT_FOUND",
                message="Ingestion proposal not found",
                status_code=404,
            )

        payload = _decode_json_dict(row["proposal_json"])
        try:
            proposal = IngestionProposalPayload.model_validate(payload)
        except Exception as exc:
            raise IngestionPlanningError(
                code="INGESTION_PROPOSAL_INVALID",
                message="Persisted proposal payload is invalid",
                status_code=500,
            ) from exc
        return row, proposal

    def _load_latest_approval_event(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        proposal_id: str,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT payload
            FROM ingestion_events
            WHERE job_id = ? AND event_type = 'proposal_approved'
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="INGESTION_APPROVAL_NOT_FOUND",
                message="Proposal has not been approved",
                status_code=409,
            )
        payload = _decode_json_dict(row["payload"])
        if str(payload.get("proposal_id", "")).strip() != proposal_id:
            raise IngestionPlanningError(
                code="INGESTION_APPROVAL_MISMATCH",
                message="Proposal approval context is not bound to this proposal",
                status_code=409,
            )
        required = (
            "approved_action",
            "target_table",
            "validated_sql",
            "validated_sql_hash",
            "dry_run_summary",
        )
        for key in required:
            if key not in payload:
                raise IngestionPlanningError(
                    code="INGESTION_APPROVAL_INVALID",
                    message="Approval payload is incomplete",
                    status_code=500,
                )
        return payload

    def _resolve_approved_target(
        self,
        *,
        proposal_payload: IngestionProposalPayload,
        approved_action: str,
        overrides: IngestionApprovalOverrides | None,
    ) -> tuple[str, str]:
        override_target = (overrides.target_table if overrides else None) or None
        override_time_grain = (overrides.time_grain if overrides else None) or None

        if approved_action == "update_existing":
            candidate = (override_target or proposal_payload.target_table or "").strip().lower()
            if not candidate:
                raise IngestionPlanningError(
                    code="TARGET_TABLE_REQUIRED",
                    message="target_table is required for update_existing",
                    status_code=422,
                )
            if not SAFE_IDENTIFIER_RE.match(candidate):
                raise IngestionPlanningError(
                    code="TARGET_TABLE_INVALID",
                    message="target_table must be a valid SQL identifier",
                    status_code=422,
                )
            return candidate, "none"

        time_grain = override_time_grain or proposal_payload.time_grain
        base_target = (
            override_target
            or proposal_payload.target_table
            or f"{proposal_payload.business_type}_ingestion"
        ).strip().lower()
        if not SAFE_IDENTIFIER_RE.match(base_target):
            raise IngestionPlanningError(
                code="TARGET_TABLE_INVALID",
                message="target_table must be a valid SQL identifier",
                status_code=422,
            )

        if approved_action == "new_table":
            if override_target:
                return base_target, "none"
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d")
            return f"{base_target}_{suffix}", "none"

        if approved_action == "time_partitioned_new_table":
            if override_target:
                return base_target, time_grain
            suffix = self._partition_suffix(time_grain)
            return f"{base_target}_{suffix}", time_grain

        raise IngestionPlanningError(
            code="WRITE_ACTION_UNSUPPORTED",
            message=f"Unsupported approved action: {approved_action}",
            status_code=422,
        )

    @staticmethod
    def _partition_suffix(time_grain: str) -> str:
        now = datetime.now(timezone.utc)
        if time_grain == "year":
            return now.strftime("%Y")
        if time_grain == "quarter":
            quarter = ((now.month - 1) // 3) + 1
            return f"{now.year}q{quarter}"
        return now.strftime("%Y%m")

    def _build_validated_sql(
        self,
        *,
        approved_action: str,
        target_table: str,
        staging_table: str,
        proposal_payload: IngestionProposalPayload,
    ) -> str:
        mapping_values = [
            str(value).strip().lower()
            for value in proposal_payload.column_mapping.values()
            if str(value).strip()
        ]
        match_columns = [
            str(value).strip().lower()
            for value in proposal_payload.match_columns
            if str(value).strip()
        ]
        ordered_columns = self._dedupe_preserve_order([*mapping_values, *match_columns])
        safe_columns = [column for column in ordered_columns if SAFE_IDENTIFIER_RE.match(column)]
        if not safe_columns:
            safe_columns = self._dedupe_preserve_order(match_columns)
        if not safe_columns:
            raise IngestionPlanningError(
                code="COLUMN_MAPPING_INVALID",
                message="Cannot build write SQL without valid mapped columns",
                status_code=422,
            )

        if approved_action == "update_existing":
            if not match_columns:
                raise IngestionPlanningError(
                    code="MATCH_COLUMNS_REQUIRED",
                    message="match_columns are required for update_existing",
                    status_code=422,
                )
            safe_match_columns = [value for value in match_columns if SAFE_IDENTIFIER_RE.match(value)]
            if not safe_match_columns:
                raise IngestionPlanningError(
                    code="MATCH_COLUMNS_INVALID",
                    message="match_columns must be valid SQL identifiers",
                    status_code=422,
                )
            match_expr = " AND ".join([f"t.{value} = s.{value}" for value in safe_match_columns])
            update_columns = [value for value in safe_columns if value not in set(safe_match_columns)]
            if not update_columns:
                update_columns = list(safe_columns)
            update_expr = ", ".join([f"{value} = s.{value}" for value in update_columns])
            insert_cols = ", ".join(safe_columns)
            insert_vals = ", ".join([f"s.{value}" for value in safe_columns])
            return (
                f"MERGE INTO {target_table} AS t\n"
                f"USING {staging_table} AS s\n"
                f"ON {match_expr}\n"
                f"WHEN MATCHED THEN UPDATE SET {update_expr}\n"
                f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
            )

        select_cols = ", ".join(safe_columns)
        return (
            f"CREATE TABLE {target_table} AS\n"
            f"SELECT {select_cols} FROM {staging_table}"
        )

    def _build_dry_run_summary(
        self,
        *,
        proposal_payload: IngestionProposalPayload,
        approved_action: str,
        target_table: str,
        time_grain: str,
    ) -> dict[str, Any]:
        preview = proposal_payload.diff_preview.model_dump(mode="json")
        predicted_insert = int(preview.get("predicted_insert_count", 0))
        predicted_update = int(preview.get("predicted_update_count", 0))
        predicted_conflict = int(preview.get("predicted_conflict_count", 0))
        affected = predicted_insert + predicted_update
        schema_warnings = [
            f"match_column_missing:{column}"
            for column in proposal_payload.match_columns
            if column not in set(proposal_payload.column_mapping.values())
        ]
        return {
            "approved_action": approved_action,
            "target_table": target_table,
            "time_grain": time_grain,
            "predicted_insert_count": max(predicted_insert, 0),
            "predicted_update_count": max(predicted_update, 0),
            "predicted_conflict_count": max(predicted_conflict, 0),
            "predicted_affected_rows": max(affected, 0),
            "schema_warnings": schema_warnings,
            "risks": list(proposal_payload.risks),
        }

    def _run_execution_transaction(
        self,
        *,
        workspace_id: str,
        job_id: str,
        target_table: str,
        approved_action: str,
        validated_sql: str,
        dry_run_summary: dict[str, Any],
        upload_info: dict[str, Any],
        proposal_payload: IngestionProposalPayload,
    ) -> dict[str, Any]:
        upload_path = Path(str(upload_info["storage_path"])).resolve()
        if not upload_path.exists():
            raise IngestionPlanningError(
                code="UPLOAD_FILE_MISSING",
                message="Uploaded file no longer exists on disk",
                status_code=500,
            )

        dataframe = self._load_execution_dataframe(
            upload_path=upload_path,
            proposal_payload=proposal_payload,
        )
        staging_table = self._staging_table_name(job_id)
        db_path = self._workspace_duckdb_path(workspace_id=workspace_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = duckdb.connect(str(db_path))
        except Exception as exc:  # pragma: no cover - defensive
            raise IngestionPlanningError(
                code="DUCKDB_CONNECT_FAILED",
                message=f"Unable to open workspace DuckDB: {exc}",
                status_code=500,
            ) from exc

        try:
            conn.execute("BEGIN TRANSACTION")
            conn.register("ingestion_upload_df", dataframe)
            conn.execute(f"CREATE OR REPLACE TEMP TABLE {staging_table} AS SELECT * FROM ingestion_upload_df")
            conn.unregister("ingestion_upload_df")

            if approved_action == "update_existing":
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {target_table} AS SELECT * FROM {staging_table} WHERE 1 = 0"
                )

            conn.execute(validated_sql)
            rows_after = int(conn.execute(f"SELECT COUNT(*) FROM {target_table}").fetchone()[0])
            conn.execute("COMMIT")
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception:  # pragma: no cover - defensive
                pass
            raise IngestionPlanningError(
                code="INGESTION_EXECUTION_FAILED",
                message=f"DuckDB execution failed: {exc}",
                status_code=500,
            ) from exc
        finally:
            conn.close()

        predicted_insert = int(dry_run_summary.get("predicted_insert_count", 0))
        predicted_update = int(dry_run_summary.get("predicted_update_count", 0))
        return {
            "success": True,
            "workspace_id": workspace_id,
            "job_id": job_id,
            "target_table": target_table,
            "execution_mode": approved_action,
            "inserted_rows": max(predicted_insert, 0),
            "updated_rows": max(predicted_update, 0),
            "affected_rows": max(predicted_insert, 0) + max(predicted_update, 0),
            "rows_after": rows_after,
            "duckdb_path": str(db_path),
            "finished_at": _utc_now(),
        }

    def _workspace_duckdb_path(self, *, workspace_id: str) -> Path:
        from ..config import get_settings

        root = get_settings().upload_dir / "agentic_ingestion" / "duckdb"
        safe_workspace = re.sub(r"[^A-Za-z0-9_-]+", "_", workspace_id).strip("_") or "workspace"
        return (root / f"{safe_workspace}.duckdb").resolve()

    def _load_execution_dataframe(
        self,
        *,
        upload_path: Path,
        proposal_payload: IngestionProposalPayload,
    ) -> pd.DataFrame:
        try:
            sheets = pd.read_excel(upload_path, sheet_name=None, dtype=object, engine="openpyxl")
        except Exception as exc:
            raise IngestionPlanningError(
                code="UPLOAD_READ_FAILED",
                message=f"Unable to read uploaded workbook: {exc}",
                status_code=500,
            ) from exc
        if not sheets:
            raise IngestionPlanningError(
                code="UPLOAD_READ_FAILED",
                message="Uploaded workbook has no readable sheets",
                status_code=500,
            )

        alias_map = {
            str(key): str(value).strip().lower()
            for key, value in proposal_payload.column_mapping.items()
            if str(key).strip() and str(value).strip()
        }
        merged_frames: list[pd.DataFrame] = []
        for frame in sheets.values():
            renamed = self._normalize_frame_columns(frame=frame, alias_map=alias_map)
            merged_frames.append(renamed)

        merged = pd.concat(merged_frames, ignore_index=True, sort=False)
        merged = merged.where(pd.notna(merged), None)
        if merged.empty:
            merged = pd.DataFrame(columns=list({*merged.columns}))
        return merged

    def _normalize_frame_columns(
        self,
        *,
        frame: pd.DataFrame,
        alias_map: dict[str, str],
    ) -> pd.DataFrame:
        rename_map: dict[str, str] = {}
        seen: set[str] = set()
        for index, column in enumerate(frame.columns):
            raw = str(column).strip()
            candidate = alias_map.get(raw) or self._normalize_identifier(raw)
            if not candidate:
                candidate = f"c_{index + 1}"
            if not SAFE_IDENTIFIER_RE.match(candidate):
                candidate = f"c_{index + 1}"
            base = candidate
            seq = 2
            while candidate in seen:
                candidate = f"{base}_{seq}"
                seq += 1
            seen.add(candidate)
            rename_map[column] = candidate
        return frame.rename(columns=rename_map)

    @staticmethod
    def _staging_table_name(job_id: str) -> str:
        return f"staging_{job_id[:12].lower()}"

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            lowered = value.strip().lower()
            if not lowered:
                continue
            if lowered in result:
                continue
            result.append(lowered)
        return result

    def _persist_proposal(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
        proposal: IngestionProposalPayload,
    ) -> str:
        row = conn.execute(
            "SELECT COALESCE(MAX(proposal_version), 0) AS max_version FROM ingestion_proposals WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        next_version = int(row["max_version"]) + 1 if row is not None else 1
        proposal_id = uuid.uuid4().hex
        serialized = proposal.model_dump(mode="json")
        conn.execute(
            """
            INSERT INTO ingestion_proposals (
                id,
                job_id,
                workspace_id,
                proposal_version,
                proposal_json,
                recommended_action,
                target_table,
                predicted_insert_count,
                predicted_update_count,
                predicted_conflict_count,
                risk_summary,
                generated_sql_draft,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                job_id,
                workspace_id,
                next_version,
                json.dumps(serialized, ensure_ascii=False),
                proposal.recommended_action,
                proposal.target_table,
                proposal.diff_preview.predicted_insert_count,
                proposal.diff_preview.predicted_update_count,
                proposal.diff_preview.predicted_conflict_count,
                json.dumps(proposal.risks, ensure_ascii=False),
                proposal.sql_draft,
                _utc_now(),
            ),
        )
        return proposal_id

    def _set_job_status(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        status: str,
        business_type_guess: str | None,
        agent_session_id: str | None,
    ) -> None:
        conn.execute(
            """
            UPDATE ingestion_jobs
            SET status = ?,
                business_type_guess = COALESCE(?, business_type_guess),
                agent_session_id = COALESCE(?, agent_session_id),
                updated_at = ?
            WHERE id = ?
            """,
            (status, business_type_guess, agent_session_id, _utc_now(), job_id),
        )

    def _upsert_catalog_entry_from_setup(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        requested_by: str,
        setup_seed: IngestionCatalogSetupSeed,
        upload_info: dict[str, Any],
    ) -> dict[str, Any]:
        self._ensure_user_record(conn=conn, user_id=requested_by)
        now = _utc_now()
        business_type = setup_seed.business_type
        table_name = setup_seed.table_name
        human_label = setup_seed.human_label
        write_mode = setup_seed.write_mode
        time_grain = setup_seed.time_grain
        description = setup_seed.description

        primary_keys = list(setup_seed.primary_keys)
        match_columns = list(setup_seed.match_columns)
        if not primary_keys and match_columns:
            primary_keys = list(match_columns)
        if not match_columns and primary_keys:
            match_columns = list(primary_keys)

        if not primary_keys and not match_columns:
            candidate_columns = [
                self._normalize_identifier(str(value))
                for value in upload_info.get("column_summary", {}).get("all_columns", [])
            ]
            candidate_columns = [value for value in candidate_columns if value]
            if candidate_columns:
                primary_keys = [candidate_columns[0]]
                match_columns = [candidate_columns[0]]

        if not primary_keys and not match_columns:
            raise IngestionPlanningError(
                code="SETUP_MATCH_COLUMNS_REQUIRED",
                message="At least one primary key or match column is required",
                status_code=422,
            )

        if setup_seed.is_active_target:
            conn.execute(
                """
                UPDATE table_catalog
                SET is_active_target = 0, updated_by = ?, updated_at = ?
                WHERE workspace_id = ? AND business_type = ?
                """,
                (requested_by, now, workspace_id, business_type),
            )

        existing = conn.execute(
            """
            SELECT id, created_by, created_at
            FROM table_catalog
            WHERE workspace_id = ? AND business_type = ? AND table_name = ?
            """,
            (workspace_id, business_type, table_name),
        ).fetchone()
        if existing is None:
            catalog_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO table_catalog (
                    id,
                    workspace_id,
                    table_name,
                    human_label,
                    business_type,
                    write_mode,
                    time_grain,
                    primary_keys,
                    match_columns,
                    is_active_target,
                    description,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    catalog_id,
                    workspace_id,
                    table_name,
                    human_label,
                    business_type,
                    write_mode,
                    time_grain,
                    json.dumps(primary_keys, ensure_ascii=False),
                    json.dumps(match_columns, ensure_ascii=False),
                    int(bool(setup_seed.is_active_target)),
                    description,
                    requested_by,
                    requested_by,
                    now,
                    now,
                ),
            )
        else:
            catalog_id = str(existing["id"])
            conn.execute(
                """
                UPDATE table_catalog
                SET
                    human_label = ?,
                    write_mode = ?,
                    time_grain = ?,
                    primary_keys = ?,
                    match_columns = ?,
                    is_active_target = ?,
                    description = ?,
                    updated_by = ?,
                    updated_at = ?
                WHERE id = ? AND workspace_id = ?
                """,
                (
                    human_label,
                    write_mode,
                    time_grain,
                    json.dumps(primary_keys, ensure_ascii=False),
                    json.dumps(match_columns, ensure_ascii=False),
                    int(bool(setup_seed.is_active_target)),
                    description,
                    requested_by,
                    now,
                    catalog_id,
                    workspace_id,
                ),
            )

        row = conn.execute(
            "SELECT * FROM table_catalog WHERE id = ? AND workspace_id = ?",
            (catalog_id, workspace_id),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="CATALOG_ENTRY_NOT_FOUND",
                message="Catalog entry not found after setup confirmation",
                status_code=500,
            )
        return self._serialize_catalog_entry(row)

    def _ensure_user_record(self, *, conn: sqlite3.Connection, user_id: str) -> None:
        normalized_user = user_id.strip()
        if not normalized_user:
            raise IngestionPlanningError(
                code="AUTH_REQUIRED",
                message="user_id is required",
                status_code=401,
            )

        now = _utc_now()
        safe_local_part = re.sub(r"[^a-z0-9._-]+", "-", normalized_user.lower()).strip("-._") or "user"
        fallback_email = f"{safe_local_part}@local.invalid"
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at
            """,
            (normalized_user, fallback_email, normalized_user, now, now),
        )

    @staticmethod
    def _normalize_identifier(raw: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip().lower()).strip("_")
        if not normalized:
            return ""
        if normalized[0].isdigit():
            normalized = f"c_{normalized}"
        return normalized

    def _tool_get_workspace_catalog(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT *
            FROM table_catalog
            WHERE workspace_id = ?
            ORDER BY is_active_target DESC, updated_at DESC
            """,
            (workspace_id,),
        ).fetchall()
        entries = [self._serialize_catalog_entry(row) for row in rows]
        return {"count": len(entries), "entries": entries}

    def _tool_list_existing_tables(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
    ) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT DISTINCT table_name
            FROM table_catalog
            WHERE workspace_id = ?
            ORDER BY table_name ASC
            """,
            (workspace_id,),
        ).fetchall()
        table_names = [str(row["table_name"]) for row in rows]
        return {"workspace_tables": table_names, "count": len(table_names)}

    def _tool_inspect_upload(self, *, conn: sqlite3.Connection, upload_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                id,
                file_name,
                storage_path,
                size_bytes,
                file_hash,
                sheet_summary,
                column_summary,
                sample_preview
            FROM ingestion_uploads
            WHERE id = ?
            """,
            (upload_id,),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="UPLOAD_NOT_FOUND",
                message="Upload not found for ingestion job",
                status_code=404,
            )
        return {
            "upload_id": str(row["id"]),
            "file_name": str(row["file_name"]),
            "storage_path": str(row["storage_path"]),
            "size_bytes": int(row["size_bytes"]),
            "file_hash": str(row["file_hash"]),
            "sheet_summary": _decode_json_dict(row["sheet_summary"]),
            "column_summary": _decode_json_dict(row["column_summary"]),
            "sample_preview": _decode_json_list(row["sample_preview"]),
        }

    def _tool_describe_table_schema_by_name(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        table_name: str,
    ) -> dict[str, Any]:
        normalized_table = table_name.strip().lower()
        row = conn.execute(
            """
            SELECT *
            FROM table_catalog
            WHERE workspace_id = ? AND table_name = ?
            ORDER BY is_active_target DESC, updated_at DESC
            LIMIT 1
            """,
            (workspace_id, normalized_table),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="CATALOG_ENTRY_NOT_FOUND",
                message="Catalog entry not found for table schema description",
                status_code=404,
            )
        target_catalog = self._serialize_catalog_entry(row)
        return {
            "table_name": target_catalog["table_name"],
            "business_type": target_catalog["business_type"],
            "primary_keys": list(target_catalog["primary_keys"]),
            "match_columns": list(target_catalog["match_columns"]),
            "write_mode": target_catalog["write_mode"],
            "time_grain": target_catalog["time_grain"],
        }

    def _tool_request_human_approval(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        stage = str(arguments.get("stage", "")).strip()
        question = str(arguments.get("question", "")).strip()
        if len(question) > 300:
            question = question[:300].rstrip()
        options = [
            str(item).strip()
            for item in arguments.get("options", [])
            if str(item).strip()
        ]
        recommended_option = str(arguments.get("recommended_option", "")).strip() or None
        if stage == "catalog_setup":
            allowed_options = CATALOG_SETUP_APPROVAL_OPTIONS
            mechanism = "catalog_setup_card"
        elif stage == "proposal_approval":
            allowed_options = DEFAULT_ACTION_OPTIONS
            mechanism = "frontend_approval_card"
        else:
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_STAGE_INVALID",
                message="Human approval stage is not supported",
                status_code=422,
            )
        if not question:
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_QUESTION_REQUIRED",
                message="Human approval question is required",
                status_code=422,
            )
        if not options or any(option not in allowed_options for option in options):
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_OPTIONS_INVALID",
                message="Human approval options are outside the designed choices",
                status_code=422,
            )
        if recommended_option and recommended_option not in options:
            raise IngestionPlanningError(
                code="HUMAN_APPROVAL_RECOMMENDATION_INVALID",
                message="Human approval recommendation must be one of the approval options",
                status_code=422,
            )
        payload = {
            "required": True,
            "status": "pending",
            "mechanism": mechanism,
            "stage": stage,
            "question": question,
            "options": options,
            "recommended_option": recommended_option,
        }
        self._insert_event(
            conn=conn,
            job_id=job_id,
            event_type="human_approval_requested",
            payload=payload,
        )
        return payload

    def _tool_build_diff_preview(
        self,
        *,
        upload_info: dict[str, Any],
        match_columns: list[str],
        action_mode: str,
    ) -> dict[str, int]:
        normalized_action = action_mode.strip().lower()
        if normalized_action not in DEFAULT_ACTION_OPTIONS:
            raise IngestionPlanningError(
                code="DIFF_PREVIEW_ACTION_INVALID",
                message="Diff preview action is not supported",
                status_code=422,
            )
        sheets = upload_info["sheet_summary"].get("sheets", [])
        total_rows = sum(int(item.get("row_count", 0)) for item in sheets)
        total_rows = max(total_rows, 1)
        if normalized_action == "cancel":
            return {
                "predicted_insert_count": 0,
                "predicted_update_count": 0,
                "predicted_conflict_count": 0,
            }
        if normalized_action in {"new_table", "time_partitioned_new_table"}:
            return {
                "predicted_insert_count": total_rows,
                "predicted_update_count": 0,
                "predicted_conflict_count": 0,
            }

        if not match_columns:
            return {
                "predicted_insert_count": total_rows,
                "predicted_update_count": 0,
                "predicted_conflict_count": min(5, max(1, total_rows // 5)),
            }

        predicted_updates = int(total_rows * 0.6)
        predicted_inserts = max(total_rows - predicted_updates, 0)
        return {
            "predicted_insert_count": predicted_inserts,
            "predicted_update_count": predicted_updates,
            "predicted_conflict_count": 0,
        }

    def _tool_generate_write_sql_draft(
        self,
        *,
        workspace_id: str,
        job_id: str,
        target_table: str,
        action_mode: str,
        match_columns: list[str],
    ) -> dict[str, str]:
        normalized_action = action_mode.strip().lower()
        if normalized_action not in {"update_existing", "time_partitioned_new_table", "new_table"}:
            raise IngestionPlanningError(
                code="SQL_DRAFT_ACTION_INVALID",
                message="SQL draft action is not supported",
                status_code=422,
            )
        safe_target = target_table if SAFE_IDENTIFIER_RE.match(target_table) else "target_table"
        staging_name = f"staging_{job_id[:12]}"
        match_expr = " AND ".join([f"t.{value} = s.{value}" for value in match_columns]) or "1 = 0"
        if normalized_action == "new_table":
            sql = (
                f"-- workspace={workspace_id}\n"
                f"CREATE TABLE {safe_target} AS\n"
                f"SELECT * FROM {staging_name};"
            )
        elif normalized_action == "time_partitioned_new_table":
            sql = (
                f"-- workspace={workspace_id}\n"
                f"CREATE TABLE {safe_target}_{{time_partition}} AS\n"
                f"SELECT * FROM {staging_name};"
            )
        else:
            sql = (
                f"-- workspace={workspace_id}\n"
                f"MERGE INTO {safe_target} AS t\n"
                f"USING {staging_name} AS s\n"
                f"ON {match_expr}\n"
                "WHEN MATCHED THEN UPDATE SET /* mapped columns */\n"
                "WHEN NOT MATCHED THEN INSERT /* mapped columns */;"
            )

        return {"sql_draft": sql}

    def _load_job_context(
        self,
        *,
        conn: sqlite3.Connection,
        workspace_id: str,
        job_id: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT
                j.id,
                j.workspace_id,
                j.upload_id,
                j.status,
                j.created_by,
                j.agent_session_id
            FROM ingestion_jobs AS j
            WHERE j.id = ? AND j.workspace_id = ?
            """,
            (job_id, workspace_id),
        ).fetchone()
        if row is None:
            raise IngestionPlanningError(
                code="INGESTION_JOB_NOT_FOUND",
                message="Ingestion job not found",
                status_code=404,
            )
        if str(row["status"]) in {"executing", "succeeded", "cancelled"}:
            raise IngestionPlanningError(
                code="INGESTION_JOB_IMMUTABLE",
                message=f"Job status does not allow planning: {row['status']}",
                status_code=409,
            )
        return row

    def _insert_event(
        self,
        *,
        conn: sqlite3.Connection,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO ingestion_events (id, job_id, event_type, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                job_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                _utc_now(),
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        from ..workspaces import get_workspace_service

        conn = sqlite3.connect(get_workspace_service().db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _serialize_catalog_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "table_name": str(row["table_name"]),
            "human_label": str(row["human_label"]),
            "business_type": str(row["business_type"]),
            "write_mode": str(row["write_mode"]),
            "time_grain": str(row["time_grain"]),
            "primary_keys": _decode_json_list(row["primary_keys"]),
            "match_columns": _decode_json_list(row["match_columns"]),
            "is_active_target": bool(row["is_active_target"]),
        }


def _decode_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if raw is None:
        return []
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if isinstance(decoded, list):
        return decoded
    return []


def _decode_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if isinstance(decoded, dict):
        return decoded
    return {}


def _canonical_ingestion_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    prefix = f"mcp__{INGESTION_SDK_MCP_SERVER_NAME}__"
    if normalized.startswith(prefix):
        return normalized[len(prefix):]
    return normalized


def _compact_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
