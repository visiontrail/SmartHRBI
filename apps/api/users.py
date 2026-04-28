from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import bcrypt as _bcrypt_lib


@dataclass(slots=True)
class UserRecord:
    id: str
    email: str
    email_lower: str
    display_name: str
    password_hash: str | None
    job_id: int | None
    status: str
    created_at: str
    last_login_at: str | None


def hash_password(password: str) -> str:
    salt = _bcrypt_lib.gensalt()
    return _bcrypt_lib.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_user(
    conn: sqlite3.Connection,
    *,
    email: str,
    display_name: str,
    password: str,
    job_id: int | None,
) -> UserRecord:
    email_lower = email.strip().lower()
    user_id = uuid.uuid4().hex
    password_hash = hash_password(password)
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO users (id, email, email_lower, display_name, password_hash, job_id,
                           status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (user_id, email.strip(), email_lower, display_name.strip(), password_hash, job_id, now, now),
    )
    conn.commit()
    return UserRecord(
        id=user_id,
        email=email.strip(),
        email_lower=email_lower,
        display_name=display_name.strip(),
        password_hash=password_hash,
        job_id=job_id,
        status="active",
        created_at=now,
        last_login_at=None,
    )


def get_user_by_email(conn: sqlite3.Connection, email: str) -> UserRecord | None:
    email_lower = email.strip().lower()
    row = conn.execute(
        """
        SELECT u.id, u.email, COALESCE(u.email_lower, LOWER(u.email)) AS email_lower,
               u.display_name, u.password_hash, u.job_id, u.status, u.created_at, u.last_login_at
        FROM users u
        WHERE COALESCE(u.email_lower, LOWER(u.email)) = ?
        """,
        (email_lower,),
    ).fetchone()
    return _row_to_record(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: str) -> UserRecord | None:
    row = conn.execute(
        """
        SELECT u.id, u.email, COALESCE(u.email_lower, LOWER(u.email)) AS email_lower,
               u.display_name, u.password_hash, u.job_id, u.status, u.created_at, u.last_login_at
        FROM users u
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    return _row_to_record(row) if row else None


def search_users(
    conn: sqlite3.Connection,
    *,
    q: str,
    limit: int = 20,
    exclude_user_id: str | None = None,
) -> list[dict[str, Any]]:
    q_lower = q.strip().lower()
    params: list[Any] = [f"{q_lower}%", f"%{q_lower}%"]
    exclude_clause = ""
    if exclude_user_id:
        exclude_clause = "AND u.id != ?"
        params.append(exclude_user_id)
    params.append(min(limit, 50))

    rows = conn.execute(
        f"""
        SELECT u.id, u.email, COALESCE(u.email_lower, LOWER(u.email)) AS email_lower,
               u.display_name, uj.label_zh AS job_label_zh, uj.label_en AS job_label_en
        FROM users u
        LEFT JOIN user_jobs uj ON uj.id = u.job_id
        WHERE (COALESCE(u.email_lower, LOWER(u.email)) LIKE ?
               OR LOWER(u.display_name) LIKE ?)
              AND u.status = 'active'
              {exclude_clause}
        ORDER BY u.display_name
        LIMIT ?
        """,
        params,
    ).fetchall()

    return [
        {
            "id": str(row["id"]),
            "email_masked": _mask_email(str(row["email_lower"])),
            "display_name": str(row["display_name"]),
            "job_label": str(row["job_label_zh"] or ""),
        }
        for row in rows
    ]


def update_last_login(conn: sqlite3.Connection, user_id: str) -> None:
    now = _utc_now()
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, user_id))
    conn.commit()


def _row_to_record(row: sqlite3.Row) -> UserRecord:
    return UserRecord(
        id=str(row["id"]),
        email=str(row["email"]),
        email_lower=str(row["email_lower"]),
        display_name=str(row["display_name"]),
        password_hash=row["password_hash"],
        job_id=row["job_id"],
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        last_login_at=row["last_login_at"],
    )


def _mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, _, domain = email.partition("@")
    show = max(1, min(2, len(local)))
    masked_local = local[:show] + "***"
    return f"{masked_local}@{domain}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
