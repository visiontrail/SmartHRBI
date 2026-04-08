from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def issue_token(
    client: TestClient,
    *,
    user_id: str,
    project_id: str,
    role: str = "admin",
    department: str | None = "HR",
    clearance: int = 9,
    expires_in: int = 3600,
) -> str:
    response = client.post(
        "/auth/login",
        json={
            "user_id": user_id,
            "project_id": project_id,
            "role": role,
            "department": department,
            "clearance": clearance,
            "expires_in": expires_in,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return str(payload["access_token"])


def auth_headers(
    client: TestClient,
    *,
    user_id: str,
    project_id: str,
    role: str = "admin",
    department: str | None = "HR",
    clearance: int = 9,
    expires_in: int = 3600,
) -> dict[str, str]:
    token = issue_token(
        client,
        user_id=user_id,
        project_id=project_id,
        role=role,
        department=department,
        clearance=clearance,
        expires_in=expires_in,
    )
    return {"Authorization": f"Bearer {token}"}


def merge_headers(*items: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for item in items:
        merged.update(item)
    return merged


def expect_error_code(response: Any, code: str, *, status_code: int) -> None:
    assert response.status_code == status_code
    detail = response.json().get("detail", {})
    assert isinstance(detail, dict)
    assert detail.get("code") == code
