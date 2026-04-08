from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .audit import get_audit_logger
from .config import get_settings

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "datasets:upload",
        "datasets:read",
        "semantic:metrics",
        "semantic:query",
        "chat:tool",
        "chat:stream",
        "views:write",
        "views:read",
        "views:share",
        "views:rollback",
        "audit:read",
        "auth:manage",
    },
    "hr": {
        "datasets:upload",
        "datasets:read",
        "semantic:metrics",
        "semantic:query",
        "chat:tool",
        "chat:stream",
        "views:write",
        "views:read",
        "views:share",
        "audit:read",
    },
    "pm": {
        "datasets:upload",
        "datasets:read",
        "semantic:metrics",
        "semantic:query",
        "chat:tool",
        "chat:stream",
        "views:write",
        "views:read",
        "views:share",
    },
    "viewer": {
        "datasets:read",
        "semantic:metrics",
        "semantic:query",
        "chat:tool",
        "chat:stream",
        "views:read",
        "views:share",
    },
}

DEFAULT_TOKEN_TTL_SECONDS = 3600
MAX_TOKEN_TTL_SECONDS = 24 * 3600

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthIdentity:
    user_id: str
    project_id: str
    role: str
    department: str | None
    clearance: int
    token_id: str
    expires_at: int


class LoginRequest(BaseModel):
    user_id: str
    project_id: str
    role: str = "viewer"
    department: str | None = None
    clearance: int = 0
    expires_in: int = Field(default=DEFAULT_TOKEN_TTL_SECONDS, ge=60, le=MAX_TOKEN_TTL_SECONDS)


class RoleUpdateRequest(BaseModel):
    role: str
    department: str | None = None
    clearance: int = 0


class AuthTokenError(Exception):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TokenExpiredError(AuthTokenError):
    pass


class TokenService:
    def __init__(self, *, secret: str) -> None:
        normalized = secret.strip()
        if not normalized:
            raise RuntimeError("AUTH_SECRET cannot be empty")
        self._secret = normalized.encode("utf-8")

    def issue_token(
        self,
        *,
        user_id: str,
        project_id: str,
        role: str,
        department: str | None,
        clearance: int,
        expires_in: int,
    ) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + expires_in
        normalized_role = normalize_role(role)
        payload = {
            "sub": user_id,
            "project_id": project_id,
            "role": normalized_role,
            "department": department,
            "clearance": int(clearance),
            "iat": now,
            "exp": expires_at,
            "jti": hashlib.sha1(f"{user_id}:{project_id}:{now}".encode("utf-8")).hexdigest()[:16],
        }
        token = self._encode(payload)
        return token, expires_at

    def verify_token(self, token: str) -> AuthIdentity:
        payload = self._decode(token)

        expires_at = int(payload.get("exp", 0))
        if expires_at <= int(time.time()):
            raise TokenExpiredError(code="TOKEN_EXPIRED", message="Authentication token has expired")

        user_id = str(payload.get("sub", "")).strip()
        project_id = str(payload.get("project_id", "")).strip()
        if not user_id or not project_id:
            raise AuthTokenError(code="TOKEN_INVALID", message="Authentication token is invalid")

        role = normalize_role(str(payload.get("role", "viewer")))
        clearance = int(payload.get("clearance", 0))
        token_id = str(payload.get("jti", "")).strip() or "unknown"

        department_raw = payload.get("department")
        department = str(department_raw).strip() if isinstance(department_raw, str) else None
        if department == "":
            department = None

        return AuthIdentity(
            user_id=user_id,
            project_id=project_id,
            role=role,
            department=department,
            clearance=clearance,
            token_id=token_id,
            expires_at=expires_at,
        )

    def _encode(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_bytes = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_bytes = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_bytes}.{payload_bytes}".encode("utf-8")
        signature = _b64url_encode(hmac.new(self._secret, signing_input, hashlib.sha256).digest())
        return f"{header_bytes}.{payload_bytes}.{signature}"

    def _decode(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthTokenError(code="TOKEN_INVALID", message="Authentication token is invalid")

        header_segment, payload_segment, signature_segment = parts
        expected_signature = _b64url_encode(
            hmac.new(
                self._secret,
                f"{header_segment}.{payload_segment}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )

        if not hmac.compare_digest(expected_signature, signature_segment):
            raise AuthTokenError(code="TOKEN_INVALID", message="Authentication token is invalid")

        try:
            header = json.loads(_b64url_decode(header_segment).decode("utf-8"))
            payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise AuthTokenError(code="TOKEN_INVALID", message="Authentication token is invalid") from exc

        if header.get("alg") != "HS256":
            raise AuthTokenError(code="TOKEN_INVALID", message="Authentication token is invalid")

        if not isinstance(payload, dict):
            raise AuthTokenError(code="TOKEN_INVALID", message="Authentication token is invalid")

        return payload


class RoleDirectory:
    def __init__(self, *, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def set_override(
        self,
        *,
        user_id: str,
        role: str,
        department: str | None,
        clearance: int,
        updated_by: str,
    ) -> dict[str, Any]:
        normalized_user = user_id.strip()
        if not normalized_user:
            raise ValueError("user_id is required")

        normalized_role = normalize_role(role)
        now = int(time.time())

        with self._lock:
            payload = self._load()
            payload[normalized_user] = {
                "role": normalized_role,
                "department": department,
                "clearance": int(clearance),
                "updated_by": updated_by,
                "updated_at": now,
            }
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload[normalized_user]

    def get_override(self, user_id: str) -> dict[str, Any] | None:
        normalized_user = user_id.strip()
        if not normalized_user:
            return None

        with self._lock:
            payload = self._load()
            raw = payload.get(normalized_user)
            if not isinstance(raw, dict):
                return None
            return dict(raw)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        decoded = json.loads(raw)
        if isinstance(decoded, dict):
            return decoded
        return {}


def has_permission(role: str, permission: str) -> bool:
    normalized_role = normalize_role(role)
    return permission in ROLE_PERMISSIONS.get(normalized_role, set())


def normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ROLE_PERMISSIONS:
        raise AuthTokenError(code="ROLE_INVALID", message="Unsupported role")
    return normalized


def require_permission(permission: str) -> Callable[[Request, AuthIdentity], AuthIdentity]:
    def dependency(
        request: Request,
        identity: AuthIdentity = Depends(get_current_identity),
    ) -> AuthIdentity:
        if has_permission(identity.role, permission):
            return identity

        get_audit_logger().log(
            event_type="authorization",
            action=permission,
            status="denied",
            severity="ALERT",
            user_id=identity.user_id,
            project_id=identity.project_id,
            resource=str(request.url.path),
            detail={"role": identity.role},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "RBAC_FORBIDDEN",
                "message": "You do not have permission to access this resource",
            },
        )

    return dependency


def ensure_scope(identity: AuthIdentity, *, user_id: str, project_id: str) -> None:
    if identity.user_id != user_id or identity.project_id != project_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SCOPE_MISMATCH",
                "message": "Token scope does not match request context",
            },
        )


def can_access_owned_resource(
    identity: AuthIdentity,
    *,
    owner_user_id: str,
    owner_project_id: str,
) -> bool:
    if identity.role == "admin":
        return True
    return identity.user_id == owner_user_id and identity.project_id == owner_project_id


def issue_access_token(payload: LoginRequest) -> dict[str, Any]:
    service = get_token_service()
    token, expires_at = service.issue_token(
        user_id=payload.user_id.strip(),
        project_id=payload.project_id.strip(),
        role=payload.role,
        department=payload.department,
        clearance=payload.clearance,
        expires_in=payload.expires_in,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": {
            "user_id": payload.user_id.strip(),
            "project_id": payload.project_id.strip(),
            "role": normalize_role(payload.role),
            "department": payload.department,
            "clearance": int(payload.clearance),
        },
    }


def get_current_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthIdentity:
    audit = get_audit_logger()

    if credentials is None or credentials.scheme.lower() != "bearer":
        audit.log(
            event_type="authentication",
            action="access",
            status="denied",
            severity="ALERT",
            resource=str(request.url.path),
            detail={"reason": "missing_token"},
        )
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Authentication is required"},
        )

    try:
        identity = get_token_service().verify_token(credentials.credentials)
    except TokenExpiredError as exc:
        audit.log(
            event_type="authentication",
            action="access",
            status="denied",
            severity="ALERT",
            resource=str(request.url.path),
            detail={"reason": exc.code},
        )
        raise HTTPException(status_code=401, detail={"code": exc.code, "message": exc.message}) from exc
    except AuthTokenError as exc:
        audit.log(
            event_type="authentication",
            action="access",
            status="denied",
            severity="ALERT",
            resource=str(request.url.path),
            detail={"reason": exc.code},
        )
        raise HTTPException(status_code=401, detail={"code": exc.code, "message": exc.message}) from exc

    override = get_role_directory().get_override(identity.user_id)
    if override:
        override_role = override.get("role", identity.role)
        identity = AuthIdentity(
            user_id=identity.user_id,
            project_id=identity.project_id,
            role=normalize_role(str(override_role)),
            department=_optional_string(override.get("department")) or identity.department,
            clearance=int(override.get("clearance", identity.clearance)),
            token_id=identity.token_id,
            expires_at=identity.expires_at,
        )

    request.state.identity = identity
    return identity


def get_role_directory() -> RoleDirectory:
    settings = get_settings()
    target = (settings.upload_dir / "auth" / "role_overrides.json").resolve()
    return _cached_role_directory(str(target))


def get_token_service() -> TokenService:
    settings = get_settings()
    return _cached_token_service(settings.auth_secret)


@lru_cache(maxsize=2)
def _cached_token_service(secret: str) -> TokenService:
    return TokenService(secret=secret)


@lru_cache(maxsize=2)
def _cached_role_directory(path_key: str) -> RoleDirectory:
    return RoleDirectory(path=Path(path_key))


def clear_auth_cache() -> None:
    _cached_token_service.cache_clear()
    _cached_role_directory.cache_clear()


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}")
