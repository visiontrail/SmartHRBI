from __future__ import annotations

import hashlib
import json
import logging
import re
import socket
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import duckdb
import pandas as pd
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from ..config import get_settings
from .models import (
    IngestionApprovalOverrides,
    IngestionCatalogSetupSeed,
    IngestionProposalPayload,
    SETUP_WRITE_MODES,
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
WRITE_MODE_TO_ACTION: dict[str, str] = {
    "update_existing": "update_existing",
    "time_partitioned_new_table": "time_partitioned_new_table",
    "new_table": "new_table",
    "append_only": "update_existing",
}
BUSINESS_TYPE_VALUES = {"roster", "project_progress", "attendance", "other"}
_BUSINESS_TYPE_SYSTEM_PROMPT = """\
You are an ingestion classifier.
Classify the uploaded workbook into exactly one business type:
- roster
- project_progress
- attendance
- other

Return only one JSON object with keys:
- business_type: one of roster|project_progress|attendance|other
- confidence: number between 0 and 1
- reasoning: short sentence (<= 120 chars)
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

            tool_trace: list[dict[str, Any]] = []
            catalog_payload = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="get_workspace_catalog",
                arguments={"workspace_id": normalized_workspace_id},
                handler=lambda: self._tool_get_workspace_catalog(
                    conn=conn,
                    workspace_id=normalized_workspace_id,
                ),
            )
            existing_tables = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="list_existing_tables",
                arguments={"workspace_id": normalized_workspace_id},
                handler=lambda: self._tool_list_existing_tables(
                    conn=conn,
                    workspace_id=normalized_workspace_id,
                ),
            )
            upload_info = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="inspect_upload",
                arguments={"upload_id": str(job["upload_id"])},
                handler=lambda: self._tool_inspect_upload(conn=conn, upload_id=str(job["upload_id"])),
            )
            business_guess = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="infer_business_type",
                arguments={"upload_id": str(job["upload_id"])},
                handler=lambda: self._tool_infer_business_type(upload_info=upload_info),
            )
            analysis_audit = {"business_type_inference": self._business_type_inference_audit(business_guess)}
            self._insert_event(
                conn=conn,
                job_id=normalized_job_id,
                event_type="business_type_inferred",
                payload={
                    "business_type": business_guess.get("business_type"),
                    "confidence": business_guess.get("confidence"),
                    "reasoning": business_guess.get("reasoning", ""),
                    "analysis_audit": analysis_audit["business_type_inference"],
                },
            )
            logger.info(
                "ingestion_business_type_inferred workspace_id=%s job_id=%s business_type=%s confidence=%s engine=%s ai_configured=%s ai_attempted=%s ai_succeeded=%s fallback_reason=%s",
                normalized_workspace_id,
                normalized_job_id,
                business_guess.get("business_type", "other"),
                business_guess.get("confidence", 0.0),
                analysis_audit["business_type_inference"]["engine"],
                analysis_audit["business_type_inference"]["ai_configured"],
                analysis_audit["business_type_inference"]["ai_attempted"],
                analysis_audit["business_type_inference"]["ai_succeeded"],
                analysis_audit["business_type_inference"]["fallback_reason"],
            )

            catalog_entries = list(catalog_payload.get("entries", []))
            candidate_catalog_entries = [
                item for item in catalog_entries if item["business_type"] == business_guess["business_type"]
            ]
            if not candidate_catalog_entries:
                setup_payload = self._build_setup_required_payload(
                    workspace_id=normalized_workspace_id,
                    job_id=normalized_job_id,
                    upload_info=upload_info,
                    business_guess=business_guess,
                    route=route,
                    trace=tool_trace,
                    analysis_audit=analysis_audit,
                )
                self._set_job_status(
                    conn=conn,
                    job_id=normalized_job_id,
                    status="awaiting_catalog_setup",
                    business_type_guess=business_guess["business_type"],
                    agent_session_id=normalized_conversation_id,
                )
                self._insert_event(
                    conn=conn,
                    job_id=normalized_job_id,
                    event_type="setup_required",
                    payload={
                        "business_type": business_guess["business_type"],
                        "confidence": business_guess["confidence"],
                        "analysis_audit": analysis_audit["business_type_inference"],
                    },
                )
                conn.commit()
                logger.info(
                    "ingestion_plan_completed workspace_id=%s job_id=%s status=awaiting_catalog_setup",
                    normalized_workspace_id,
                    normalized_job_id,
                )
                return setup_payload

            target_catalog = self._pick_target_catalog(candidate_catalog_entries)
            table_schema = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="describe_table_schema",
                arguments={"table_name": target_catalog["table_name"]},
                handler=lambda: self._tool_describe_table_schema(target_catalog=target_catalog),
            )

            recommended_action = WRITE_MODE_TO_ACTION.get(
                str(target_catalog["write_mode"]),
                "update_existing",
            )
            match_columns = list(target_catalog["match_columns"] or target_catalog["primary_keys"])
            diff_preview = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="build_diff_preview",
                arguments={
                    "upload_id": str(job["upload_id"]),
                    "target_table": target_catalog["table_name"],
                    "match_columns": match_columns,
                    "action_mode": recommended_action,
                },
                handler=lambda: self._tool_build_diff_preview(
                    upload_info=upload_info,
                    match_columns=match_columns,
                    action_mode=recommended_action,
                ),
            )
            sql_draft_payload = self._run_tool(
                conn=conn,
                job_id=normalized_job_id,
                trace=tool_trace,
                name="generate_write_sql_draft",
                arguments={
                    "target_table": target_catalog["table_name"],
                    "action_mode": recommended_action,
                },
                handler=lambda: self._tool_generate_write_sql_draft(
                    workspace_id=normalized_workspace_id,
                    job_id=normalized_job_id,
                    target_table=target_catalog["table_name"],
                    action_mode=recommended_action,
                    match_columns=match_columns,
                ),
            )

            risks = self._build_risks(
                upload_info=upload_info,
                match_columns=match_columns,
                diff_preview=diff_preview,
            )
            proposal = IngestionProposalPayload(
                business_type=business_guess["business_type"],
                confidence=business_guess["confidence"],
                recommended_action=recommended_action,
                candidate_actions=DEFAULT_ACTION_OPTIONS,
                target_table=target_catalog["table_name"],
                time_grain=target_catalog["time_grain"],
                match_columns=match_columns,
                column_mapping=self._build_column_mapping(
                    upload_info=upload_info,
                    table_schema=table_schema,
                ),
                diff_preview=diff_preview,
                risks=risks,
                explanation=(
                    "The upload matches the workspace catalog active target and can proceed "
                    "after explicit approval."
                ),
                sql_draft=sql_draft_payload["sql_draft"],
                requires_catalog_setup=False,
            )

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
                business_type_guess=business_guess["business_type"],
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
            "route": route.to_payload(),
            "existing_tables": existing_tables,
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

    @staticmethod
    def _pick_target_catalog(entries: list[dict[str, Any]]) -> dict[str, Any]:
        active = [item for item in entries if item["is_active_target"]]
        if active:
            return active[0]
        return entries[0]

    def _build_setup_required_payload(
        self,
        *,
        workspace_id: str,
        job_id: str,
        upload_info: dict[str, Any],
        business_guess: dict[str, Any],
        route: RouteDecision,
        trace: list[dict[str, Any]],
        analysis_audit: dict[str, Any],
    ) -> dict[str, Any]:
        first_columns = list(upload_info["column_summary"].get("all_columns", []))[:3]
        suggested_match = [first_columns[0]] if first_columns else []
        suggested_table_name = self._suggest_table_name(
            file_name=str(upload_info["file_name"]),
            business_type=str(business_guess["business_type"]),
        )
        suggested_write_mode = "update_existing"
        suggested_time_grain = "none"
        if business_guess["business_type"] in {"attendance", "project_progress"}:
            suggested_write_mode = "time_partitioned_new_table"
            suggested_time_grain = "month"

        return {
            "status": "awaiting_catalog_setup",
            "workspace_id": workspace_id,
            "job_id": job_id,
            "agent_guess": business_guess,
            "setup_questions": [
                {
                    "question_id": "business_type",
                    "title": "这份数据属于哪类业务？",
                    "options": ["roster", "project_progress", "attendance", "other"],
                },
                {
                    "question_id": "write_mode",
                    "title": "默认写入方式是什么？",
                    "options": list(SETUP_WRITE_MODES),
                },
                {
                    "question_id": "match_columns",
                    "title": "用于匹配更新的主键列是什么？",
                    "options": first_columns,
                },
            ],
            "suggested_catalog_seed": {
                "business_type": business_guess["business_type"],
                "table_name": suggested_table_name,
                "human_label": suggested_table_name.replace("_", " ").title(),
                "write_mode": suggested_write_mode,
                "time_grain": suggested_time_grain,
                "primary_keys": suggested_match,
                "match_columns": suggested_match,
                "is_active_target": True,
                "description": "Seed generated from upload inspection and business-type inference.",
            },
            "route": route.to_payload(),
            "tool_trace": trace,
            "analysis_audit": analysis_audit,
        }

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

    def _tool_infer_business_type(self, *, upload_info: dict[str, Any]) -> dict[str, Any]:
        columns = [
            str(value).strip().lower()
            for value in upload_info["column_summary"].get("all_columns", [])
            if str(value).strip()
        ]
        sheet_names = [
            str(item.get("sheet_name", "")).strip().lower()
            for item in upload_info["sheet_summary"].get("sheets", [])
            if str(item.get("sheet_name", "")).strip()
        ]
        text_blob = " ".join([*columns, *sheet_names, str(upload_info["file_name"]).lower()])
        keyword_guess = self._infer_business_type_with_keywords(text_blob)

        settings = get_settings()
        ai_configured = bool(
            settings.ai_api_key.strip()
            and settings.ai_model.strip()
            and settings.model_provider_url.strip()
        )
        if not ai_configured:
            keyword_guess.update(
                {
                    "inference_engine": "rules_keywords_v1",
                    "ai_configured": False,
                    "ai_attempted": False,
                    "ai_succeeded": False,
                    "fallback_reason": "ai_not_configured",
                }
            )
            return keyword_guess

        try:
            llm_guess = self._infer_business_type_with_llm(
                file_name=str(upload_info.get("file_name", "")),
                columns=columns,
                sheet_names=sheet_names,
                sample_preview=upload_info.get("sample_preview", []),
                model=settings.ai_model,
                base_url=settings.model_provider_url,
                api_key=settings.ai_api_key,
                timeout_seconds=settings.ai_timeout_seconds,
            )
            llm_guess.update(
                {
                    "inference_engine": "llm_classifier_v1",
                    "ai_configured": True,
                    "ai_attempted": True,
                    "ai_succeeded": True,
                    "fallback_reason": "",
                    "keyword_fallback": keyword_guess,
                }
            )
            return llm_guess
        except Exception as exc:
            logger.warning(
                "ingestion_business_type_llm_fallback file_name=%s error_type=%s error=%s",
                str(upload_info.get("file_name", "")),
                type(exc).__name__,
                str(exc),
            )
            keyword_guess.update(
                {
                    "inference_engine": "rules_keywords_v1",
                    "ai_configured": True,
                    "ai_attempted": True,
                    "ai_succeeded": False,
                    "fallback_reason": f"llm_error:{type(exc).__name__}",
                }
            )
            return keyword_guess

    @staticmethod
    def _infer_business_type_with_keywords(text_blob: str) -> dict[str, Any]:
        business_type = "other"
        confidence = 0.55
        reason = "No strong business-type keyword match was found."
        keyword_groups = [
            ("roster", ("employee", "员工", "花名册", "department", "部门", "hire", "入职")),
            ("project_progress", ("project", "milestone", "progress", "项目", "进度", "里程碑")),
            ("attendance", ("attendance", "考勤", "打卡", "absence", "出勤", "迟到")),
        ]
        matched_keywords: list[str] = []
        for candidate, keywords in keyword_groups:
            matched_keywords = [keyword for keyword in keywords if keyword in text_blob]
            if matched_keywords:
                business_type = candidate
                confidence = min(0.95, 0.62 + len(matched_keywords) * 0.1)
                reason = f"Matched keywords for {candidate}: {len(matched_keywords)}"
                break

        return {
            "business_type": business_type,
            "confidence": round(confidence, 2),
            "reasoning": reason,
            "matched_keywords": matched_keywords,
        }

    def _infer_business_type_with_llm(
        self,
        *,
        file_name: str,
        columns: list[str],
        sheet_names: list[str],
        sample_preview: list[Any],
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        endpoint = _chat_completions_endpoint(base_url)
        payload = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _BUSINESS_TYPE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "file_name": file_name,
                            "columns": columns[:80],
                            "sheet_names": sheet_names[:20],
                            "sample_preview": sample_preview[:2],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
        }
        request = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")

        started_at = time.perf_counter()
        try:
            with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except TimeoutError as exc:
            raise RuntimeError("timeout") from exc
        except socket.timeout as exc:
            raise RuntimeError("timeout") from exc
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            raise RuntimeError(f"http_{exc.code}:{details or exc.reason}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"url_error:{exc.reason}") from exc

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "ingestion_business_type_llm_response file_name=%s endpoint=%s model=%s elapsed_ms=%s",
            file_name,
            endpoint,
            model,
            elapsed_ms,
        )
        data = _decode_json_dict(raw)
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("empty_choices")
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        text_content = _content_to_text(content)
        parsed = _json_from_text(text_content)

        business_type = str(parsed.get("business_type", "")).strip()
        if business_type not in BUSINESS_TYPE_VALUES:
            raise RuntimeError(f"invalid_business_type:{business_type or 'empty'}")
        confidence = _clamp_confidence(parsed.get("confidence"))
        reasoning = str(parsed.get("reasoning", "")).strip() or "LLM classification result."
        return {
            "business_type": business_type,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    @staticmethod
    def _business_type_inference_audit(business_guess: dict[str, Any]) -> dict[str, Any]:
        return {
            "engine": str(business_guess.get("inference_engine", "rules_keywords_v1")),
            "ai_configured": bool(business_guess.get("ai_configured", False)),
            "ai_attempted": bool(business_guess.get("ai_attempted", False)),
            "ai_succeeded": bool(business_guess.get("ai_succeeded", False)),
            "fallback_reason": str(business_guess.get("fallback_reason", "")),
        }

    def _tool_describe_table_schema(self, *, target_catalog: dict[str, Any]) -> dict[str, Any]:
        return {
            "table_name": target_catalog["table_name"],
            "business_type": target_catalog["business_type"],
            "primary_keys": list(target_catalog["primary_keys"]),
            "match_columns": list(target_catalog["match_columns"]),
            "write_mode": target_catalog["write_mode"],
            "time_grain": target_catalog["time_grain"],
        }

    def _tool_build_diff_preview(
        self,
        *,
        upload_info: dict[str, Any],
        match_columns: list[str],
        action_mode: str,
    ) -> dict[str, int]:
        sheets = upload_info["sheet_summary"].get("sheets", [])
        total_rows = sum(int(item.get("row_count", 0)) for item in sheets)
        total_rows = max(total_rows, 1)
        if action_mode == "new_table":
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
        safe_target = target_table if SAFE_IDENTIFIER_RE.match(target_table) else "target_table"
        staging_name = f"staging_{job_id[:12]}"
        match_expr = " AND ".join([f"t.{value} = s.{value}" for value in match_columns]) or "1 = 0"
        if action_mode == "new_table":
            sql = (
                f"-- workspace={workspace_id}\n"
                f"CREATE TABLE {safe_target} AS\n"
                f"SELECT * FROM {staging_name};"
            )
        elif action_mode == "time_partitioned_new_table":
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

    def _build_column_mapping(
        self,
        *,
        upload_info: dict[str, Any],
        table_schema: dict[str, Any],
    ) -> dict[str, str]:
        all_columns = [
            str(value).strip()
            for value in upload_info["column_summary"].get("all_columns", [])
            if str(value).strip()
        ]
        target_candidates = set(str(value).strip() for value in table_schema.get("match_columns", []))
        target_candidates.update(str(value).strip() for value in table_schema.get("primary_keys", []))
        alias_map = {
            "员工编号": "employee_id",
            "工号": "employee_id",
            "姓名": "employee_name",
            "部门": "department",
            "项目编号": "project_id",
            "项目名称": "project_name",
            "月份": "month",
        }
        mapping: dict[str, str] = {}
        for column in all_columns:
            normalized = alias_map.get(column, column.strip().lower().replace(" ", "_"))
            if target_candidates and normalized not in target_candidates:
                continue
            mapping[column] = normalized

        if not mapping:
            for column in all_columns:
                mapping[column] = alias_map.get(column, column.strip().lower().replace(" ", "_"))
        return mapping

    def _build_risks(
        self,
        *,
        upload_info: dict[str, Any],
        match_columns: list[str],
        diff_preview: dict[str, int],
    ) -> list[str]:
        risks: list[str] = []
        if not match_columns:
            risks.append("No match columns configured; update matching may be unreliable.")
        if diff_preview["predicted_conflict_count"] > 0:
            risks.append(
                f"{diff_preview['predicted_conflict_count']} potential conflicts were detected in dry preview."
            )
        if not upload_info["sample_preview"]:
            risks.append("Workbook sample preview is empty.")
        return risks

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

    @staticmethod
    def _suggest_table_name(*, file_name: str, business_type: str) -> str:
        base = PathLike.basename_without_extension(file_name)
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_").lower()
        if not normalized:
            normalized = business_type
        if SAFE_IDENTIFIER_RE.match(normalized):
            return normalized
        candidate = f"{business_type}_table"
        return candidate if SAFE_IDENTIFIER_RE.match(candidate) else "ingestion_table"

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


class PathLike:
    @staticmethod
    def basename_without_extension(raw: str) -> str:
        parts = re.split(r"[\\/]", raw.strip())
        leaf = parts[-1] if parts else raw
        if "." not in leaf:
            return leaf
        return leaf.rsplit(".", 1)[0]


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


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks).strip()
    return ""


def _json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
    stripped = re.sub(r"\n?```$", "", stripped)
    if not stripped:
        raise RuntimeError("empty_content")
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        raise RuntimeError("missing_json_object")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid_json_object") from exc
    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError("json_not_object")


def _clamp_confidence(raw: Any) -> float:
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        parsed = 0.0
    return round(max(0.0, min(parsed, 1.0)), 2)


def _compact_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
