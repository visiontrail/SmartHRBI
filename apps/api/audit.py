from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from .config import get_settings


@dataclass(slots=True)
class AuditEvent:
    event_id: str
    timestamp: str
    event_type: str
    action: str
    status: str
    severity: str
    user_id: str | None
    project_id: str | None
    resource: str | None
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "action": self.action,
            "status": self.status,
            "severity": self.severity,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "resource": self.resource,
            "detail": self.detail,
        }


class AuditLogger:
    def __init__(self, *, events_file: Path) -> None:
        self.events_file = events_file
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def log(
        self,
        *,
        event_type: str,
        action: str,
        status: str,
        user_id: str | None = None,
        project_id: str | None = None,
        resource: str | None = None,
        severity: str = "INFO",
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = AuditEvent(
            event_id=uuid.uuid4().hex,
            timestamp=_utc_now(),
            event_type=event_type,
            action=action,
            status=status,
            severity=severity,
            user_id=user_id,
            project_id=project_id,
            resource=resource,
            detail=detail or {},
        )

        line = json.dumps(event.to_dict(), ensure_ascii=False)
        with self._lock, self.events_file.open("a", encoding="utf-8") as fp:
            fp.write(f"{line}\n")
        return event.to_dict()

    def query(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 1000))
        if not self.events_file.exists():
            return []

        with self._lock, self.events_file.open("r", encoding="utf-8") as fp:
            rows = [json.loads(line) for line in fp if line.strip()]

        filtered: list[dict[str, Any]] = []
        for item in reversed(rows):
            if user_id and str(item.get("user_id")) != user_id:
                continue
            if action and str(item.get("action")) != action:
                continue
            if status and str(item.get("status")) != status:
                continue
            if severity and str(item.get("severity")) != severity:
                continue
            filtered.append(item)
            if len(filtered) >= safe_limit:
                break

        return filtered


@lru_cache(maxsize=2)
def _cached_audit_logger(path_key: str) -> AuditLogger:
    return AuditLogger(events_file=Path(path_key))


def get_audit_logger() -> AuditLogger:
    settings = get_settings()
    events_file = (settings.upload_dir / "audit" / "security_events.log").resolve()
    return _cached_audit_logger(str(events_file))


def clear_audit_logger_cache() -> None:
    _cached_audit_logger.cache_clear()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
