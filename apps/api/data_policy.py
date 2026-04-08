from __future__ import annotations

import re
from typing import Any

SENSITIVE_COLUMN_RULES: dict[str, dict[str, set[str]]] = {
    "salary": {"allowed_roles": {"admin", "hr"}},
    "bonus": {"allowed_roles": {"admin", "hr"}},
    "ssn": {"allowed_roles": {"admin", "hr"}},
    "bank_account": {"allowed_roles": {"admin", "hr"}},
}

REDACTED_VALUE = "[REDACTED]"


def forbidden_sensitive_columns(role: str) -> set[str]:
    normalized_role = role.strip().lower()
    blocked: set[str] = set()
    for column, rule in SENSITIVE_COLUMN_RULES.items():
        allowed_roles = rule.get("allowed_roles", set())
        if normalized_role not in allowed_roles:
            blocked.add(column)
    return blocked


def redact_rows(rows: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
    blocked = forbidden_sensitive_columns(role)
    if not blocked:
        return rows

    redacted: list[dict[str, Any]] = []
    for row in rows:
        masked_row: dict[str, Any] = {}
        for key, value in row.items():
            if _is_sensitive_key(key, blocked):
                masked_row[key] = REDACTED_VALUE
            else:
                masked_row[key] = value
        redacted.append(masked_row)
    return redacted


def filter_schema_columns(columns: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
    blocked = forbidden_sensitive_columns(role)
    if not blocked:
        return columns
    return [item for item in columns if not _is_sensitive_key(str(item.get("name", "")), blocked)]


def redact_structure(payload: Any, *, role: str) -> Any:
    blocked = forbidden_sensitive_columns(role)
    if not blocked:
        return payload
    return _redact_value(payload, blocked)


def _redact_value(value: Any, blocked: set[str]) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            if _is_sensitive_key(key, blocked):
                redacted[key] = REDACTED_VALUE
                continue
            redacted[key] = _redact_value(nested, blocked)
        return redacted

    if isinstance(value, list):
        return [_redact_value(item, blocked) for item in value]

    return value


def _normalize_identifier(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "_", lowered)
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered


def _is_sensitive_key(raw_key: str, blocked: set[str]) -> bool:
    normalized = _normalize_identifier(raw_key)
    if normalized in blocked:
        return True

    return any(
        normalized.startswith(f"{column}_") or normalized.endswith(f"_{column}")
        for column in blocked
    )
