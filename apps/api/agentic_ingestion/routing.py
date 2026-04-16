from __future__ import annotations

from dataclasses import dataclass

WRITE_INTENT_KEYWORDS = (
    "上传",
    "导入",
    "写入",
    "更新花名册",
    "更新项目进度",
    "replace",
    "append",
    "merge",
    "import",
    "upload",
    "ingest",
)
INGESTION_ACTIVE_STATUSES = frozenset(
    {
        "uploaded",
        "planning",
        "awaiting_catalog_setup",
        "awaiting_user_approval",
        "approved",
        "executing",
    }
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: str
    reason: str

    def to_payload(self) -> dict[str, str]:
        return {"route": self.route, "reason": self.reason}


def select_agent_route(
    *,
    message: str | None,
    has_files: bool,
    ingestion_job_status: str | None,
) -> RouteDecision:
    if has_files:
        return RouteDecision(route="write_ingestion", reason="request_has_attachments")

    if (ingestion_job_status or "").strip() in INGESTION_ACTIVE_STATUSES:
        return RouteDecision(route="write_ingestion", reason="ingestion_lifecycle_active")

    normalized_message = (message or "").strip().lower()
    if normalized_message and any(keyword in normalized_message for keyword in WRITE_INTENT_KEYWORDS):
        return RouteDecision(route="write_ingestion", reason="matched_write_intent_keyword")

    return RouteDecision(route="query", reason="default_query_route")
