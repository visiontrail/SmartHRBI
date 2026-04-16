from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .models import IngestionProposalPayload
from .routing import RouteDecision, select_agent_route

SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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
class WriteIngestionAgentRuntime:
    stage: str = "M4"

    def health_summary(self) -> str:
        return "Write ingestion runtime supports planning/proposal lifecycle"

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
                    },
                )
                conn.commit()
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

        return {
            "status": "awaiting_user_approval",
            "workspace_id": normalized_workspace_id,
            "job_id": normalized_job_id,
            "proposal_id": proposal_id,
            "proposal_json": proposal.model_dump(mode="json"),
            "route": route.to_payload(),
            "existing_tables": existing_tables,
            "tool_trace": tool_trace,
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
        self._insert_event(
            conn=conn,
            job_id=job_id,
            event_type="tool_use",
            payload={"tool_name": name, "arguments": arguments},
        )
        result = handler()
        self._insert_event(
            conn=conn,
            job_id=job_id,
            event_type="tool_result",
            payload={"tool_name": name, "result": result},
        )
        trace.append({"tool_name": name, "arguments": arguments, "result": result})
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
                    "options": ["update_existing", "time_partitioned_new_table", "new_table"],
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
        }

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

        business_type = "other"
        confidence = 0.55
        reason = "No strong business-type keyword match was found."
        keyword_groups = [
            ("roster", ("employee", "员工", "花名册", "department", "部门", "hire", "入职")),
            ("project_progress", ("project", "milestone", "progress", "项目", "进度", "里程碑")),
            ("attendance", ("attendance", "考勤", "打卡", "absence", "出勤", "迟到")),
        ]
        for candidate, keywords in keyword_groups:
            score = sum(1 for keyword in keywords if keyword in text_blob)
            if score > 0:
                business_type = candidate
                confidence = min(0.95, 0.62 + score * 0.1)
                reason = f"Matched keywords for {candidate}: {score}"
                break

        return {
            "business_type": business_type,
            "confidence": round(confidence, 2),
            "reasoning": reason,
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
