from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from .audit import get_audit_logger
from .auth import (
    AuthIdentity,
    AuthTokenError,
    LoginRequest,
    RoleUpdateRequest,
    can_access_owned_resource,
    ensure_scope,
    get_role_directory,
    issue_access_token,
    require_permission,
)
from .chat import ChatStreamRequest, get_chat_stream_service
from .config import get_settings
from .data_policy import forbidden_sensitive_columns, redact_rows, redact_structure
from .datasets import DatasetUploadError, get_dataset_service
from .security import (
    AccessContext,
    QueryAccessError,
    RLSInjector,
    RLSError,
    SQLGuardError,
    SQLReadOnlyValidator,
    secure_query_sql,
)
from .semantic import (
    IntentParser,
    MetricCompileError,
    QueryFilter,
    SemanticQueryAST,
    get_metric_compiler,
    get_semantic_registry,
)
from .tool_calling import ToolCallRequest, get_tool_calling_service
from .views import (
    RollbackInput,
    SaveViewInput,
    ViewStorageError,
    get_view_storage_service,
)

app = FastAPI(title="SmartHRBI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SemanticFilterInput(BaseModel):
    field: str
    op: str = "eq"
    value: Any

    def to_query_filter(self) -> QueryFilter:
        return QueryFilter(field=self.field, op=self.op, value=self.value)


class SemanticQueryRequest(BaseModel):
    user_id: str
    project_id: str
    dataset_table: str
    metric: str | None = None
    intent: str | None = None
    group_by: list[str] = Field(default_factory=list)
    filters: list[SemanticFilterInput] = Field(default_factory=list)
    role: str = "viewer"
    department: str | None = None
    clearance: int = 0
    limit: int | None = None


class ChatStreamAPIRequest(ChatStreamRequest):
    pass


class SaveViewRequest(BaseModel):
    user_id: str
    project_id: str
    dataset_table: str
    role: str = "viewer"
    department: str | None = None
    clearance: int = 0
    title: str = "Saved View"
    ai_state: dict[str, Any]
    conversation_id: str | None = None
    view_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackViewRequest(BaseModel):
    user_id: str
    project_id: str
    role: str = "viewer"
    department: str | None = None
    clearance: int = 0


def configure_application_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    app_logger = logging.getLogger("smarthrbi")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")

    app_logger.setLevel(level)
    if uvicorn_error_logger.handlers:
        app_logger.handlers = uvicorn_error_logger.handlers
        app_logger.propagate = False
    elif not app_logger.handlers:
        logging.basicConfig(level=level)
        app_logger.propagate = True


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    configure_application_logging(settings.log_level)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("smarthrbi")
    logger.info(
        "application_logging_configured level=%s upload_dir=%s",
        settings.log_level,
        settings.upload_dir,
    )
    logger.info(
        "chat_runtime_config chat_engine=%s allowlist_enabled=%s claude_agent_sdk_enabled=%s "
        "agent_max_tool_steps=%s agent_max_sql_rows=%s agent_timeout_seconds=%s",
        settings.chat_engine,
        bool(settings.chat_engine_user_allowlist),
        settings.claude_agent_sdk_enabled,
        settings.agent_max_tool_steps,
        settings.agent_max_sql_rows,
        settings.agent_timeout_seconds,
    )


@app.post("/auth/login")
async def auth_login(request: LoginRequest) -> dict[str, Any]:
    if not request.user_id.strip() or not request.project_id.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_LOGIN_PAYLOAD",
                "message": "user_id and project_id are required",
            },
        )

    audit = get_audit_logger()
    try:
        payload = issue_access_token(request)
    except AuthTokenError as exc:
        audit.log(
            event_type="authentication",
            action="login",
            status="denied",
            severity="ALERT",
            user_id=request.user_id,
            project_id=request.project_id,
            detail={"reason": exc.code},
        )
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    audit.log(
        event_type="authentication",
        action="login",
        status="success",
        user_id=request.user_id,
        project_id=request.project_id,
        detail={"role": payload["user"]["role"]},
    )
    return payload


@app.post("/auth/roles/{user_id}")
async def update_user_role(
    user_id: str,
    request: RoleUpdateRequest,
    identity: AuthIdentity = Depends(require_permission("auth:manage")),
) -> dict[str, Any]:
    audit = get_audit_logger()
    try:
        override = get_role_directory().set_override(
            user_id=user_id,
            role=request.role,
            department=request.department,
            clearance=request.clearance,
            updated_by=identity.user_id,
        )
    except (AuthTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "ROLE_UPDATE_INVALID", "message": str(exc)},
        ) from exc

    audit.log(
        event_type="authorization",
        action="role_update",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={"target_user_id": user_id, "role": override["role"]},
    )
    return {"user_id": user_id, "override": override}


@app.get("/audit/events")
async def list_audit_events(
    user_id: str | None = None,
    action: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    identity: AuthIdentity = Depends(require_permission("audit:read")),
) -> dict[str, Any]:
    _ = identity
    events = get_audit_logger().query(
        user_id=user_id,
        action=action,
        status=status,
        severity=severity,
        limit=limit,
    )
    return {"count": len(events), "events": events}


@app.post("/datasets/upload")
async def upload_datasets(
    user_id: str = Form(...),
    project_id: str = Form(...),
    files: list[UploadFile] = File(...),
    identity: AuthIdentity = Depends(require_permission("datasets:upload")),
) -> dict[str, object]:
    ensure_scope(identity, user_id=user_id, project_id=project_id)
    settings = get_settings()
    service = get_dataset_service(
        settings.upload_dir,
        ai_api_key=settings.ai_api_key,
        ai_model=settings.ai_model,
        ai_timeout=settings.ai_timeout_seconds,
    )
    audit = get_audit_logger()

    try:
        result = await service.upload_files(user_id=user_id, project_id=project_id, files=files)
    except DatasetUploadError as exc:
        audit.log(
            event_type="dataset",
            action="upload",
            status="failed",
            user_id=user_id,
            project_id=project_id,
            detail={"code": exc.code},
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    audit.log(
        event_type="dataset",
        action="upload",
        status="success",
        user_id=user_id,
        project_id=project_id,
        detail={"batch_id": result["batch_id"], "file_count": result["file_count"]},
    )
    return result


@app.get("/datasets/{batch_id}/quality-report")
async def get_quality_report(
    batch_id: str,
    identity: AuthIdentity = Depends(require_permission("datasets:read")),
) -> dict[str, object]:
    settings = get_settings()
    service = get_dataset_service(settings.upload_dir)

    try:
        metadata = service.storage.load_metadata(batch_id)
    except DatasetUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    owner_project_id = str(metadata.get("project_id", ""))
    if identity.role != "admin" and owner_project_id != identity.project_id:
        get_audit_logger().log(
            event_type="authorization",
            action="dataset:quality_report",
            status="denied",
            severity="ALERT",
            user_id=identity.user_id,
            project_id=identity.project_id,
            detail={"batch_id": batch_id},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "RBAC_FORBIDDEN",
                "message": "You do not have permission to access this resource",
            },
        )

    return metadata["quality_report"]


@app.get("/semantic/metrics")
async def list_semantic_metrics(
    identity: AuthIdentity = Depends(require_permission("semantic:metrics")),
) -> dict[str, object]:
    _ = identity
    registry = get_semantic_registry()
    metrics = registry.list_metrics()
    return {"count": len(metrics), "metrics": metrics}


@app.post("/semantic/query")
async def semantic_query(
    request: SemanticQueryRequest,
    identity: AuthIdentity = Depends(require_permission("semantic:query")),
) -> dict[str, object]:
    ensure_scope(identity, user_id=request.user_id, project_id=request.project_id)

    settings = get_settings()
    registry = get_semantic_registry()
    compiler = get_metric_compiler()
    parser = IntentParser(registry)
    dataset_service = get_dataset_service(settings.upload_dir)
    audit = get_audit_logger()

    try:
        query_ast = _build_query_ast(request=request, parser=parser)
        compiled = compiler.compile(query_ast, table_override=request.dataset_table)
    except MetricCompileError as exc:
        raise HTTPException(status_code=422, detail=exc.to_detail()) from exc

    guard = SQLReadOnlyValidator(
        allowed_tables={request.dataset_table},
        sensitive_tables={"raw_payroll", "security_audit_log"},
        sensitive_columns=forbidden_sensitive_columns(identity.role),
    )
    rls_injector = RLSInjector()
    access_context = AccessContext(
        user_id=identity.user_id,
        role=identity.role,
        department=identity.department,
        clearance=identity.clearance,
    )

    try:
        secure_sql = secure_query_sql(
            compiled.sql,
            context=access_context,
            guard=guard,
            rls_injector=rls_injector,
        )
    except QueryAccessError as exc:
        audit.log(
            event_type="query",
            action="semantic_query",
            status="denied",
            severity="ALERT",
            user_id=identity.user_id,
            project_id=identity.project_id,
            detail={"code": exc.code},
        )
        raise HTTPException(status_code=403, detail=exc.to_detail()) from exc
    except (SQLGuardError, RLSError) as exc:
        raise HTTPException(status_code=400, detail=exc.to_detail()) from exc

    try:
        with dataset_service.session_manager.connection(identity.user_id, identity.project_id) as conn:
            cursor = conn.execute(secure_sql)
            columns = [column[0] for column in (cursor.description or [])]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "QUERY_EXECUTION_FAILED",
                "message": "Failed to execute semantic query",
            },
        ) from exc

    safe_rows = redact_rows(rows, role=identity.role)
    audit.log(
        event_type="query",
        action="semantic_query",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={"metric": compiled.metric, "row_count": len(safe_rows)},
    )

    return {
        "metric": compiled.metric,
        "query_ast": {
            "metric": query_ast.metric,
            "group_by": query_ast.group_by,
            "filters": [
                {"field": item.field, "op": item.op, "value": item.value}
                for item in query_ast.filters
            ],
            "limit": query_ast.limit,
        },
        "sql": secure_sql,
        "explain": compiled.explain,
        "row_count": len(safe_rows),
        "rows": safe_rows,
    }


@app.post("/chat/tool-call")
async def chat_tool_call(
    request: ToolCallRequest,
    identity: AuthIdentity = Depends(require_permission("chat:tool")),
) -> dict[str, object]:
    ensure_scope(identity, user_id=request.user_id, project_id=request.project_id)

    enforced_request = request.model_copy(
        update={
            "user_id": identity.user_id,
            "project_id": identity.project_id,
            "role": identity.role,
            "department": identity.department,
            "clearance": identity.clearance,
        }
    )

    service = get_tool_calling_service()
    response = service.invoke(enforced_request)

    status = "success" if response.status == "success" else "failed"
    severity = "INFO"
    if response.error and response.error.get("code") in {"ACCESS_DENIED", "RBAC_FORBIDDEN"}:
        status = "denied"
        severity = "ALERT"

    get_audit_logger().log(
        event_type="query",
        action="tool_call",
        status=status,
        severity=severity,
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={"tool": response.tool_name, "attempts": response.attempts},
    )
    return response.model_dump()


@app.post("/chat/stream")
async def chat_stream(
    request: ChatStreamAPIRequest,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    identity: AuthIdentity = Depends(require_permission("chat:stream")),
) -> StreamingResponse:
    ensure_scope(identity, user_id=request.user_id, project_id=request.project_id)

    enforced_request = request.model_copy(
        update={
            "user_id": identity.user_id,
            "project_id": identity.project_id,
            "role": identity.role,
            "department": identity.department,
            "clearance": identity.clearance,
        }
    )

    get_audit_logger().log(
        event_type="query",
        action="chat_stream",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={
            "conversation_id": enforced_request.conversation_id,
            "chat_engine": get_settings().chat_engine,
        },
    )

    service = get_chat_stream_service()
    stream = service.stream(enforced_request, last_event_id_header=last_event_id)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/views")
async def save_view(
    request: SaveViewRequest,
    identity: AuthIdentity = Depends(require_permission("views:write")),
) -> dict[str, Any]:
    ensure_scope(identity, user_id=request.user_id, project_id=request.project_id)

    service = get_view_storage_service()
    safe_ai_state = redact_structure(request.ai_state, role=identity.role)
    try:
        result = service.save_view(
            SaveViewInput(
                user_id=identity.user_id,
                project_id=identity.project_id,
                dataset_table=request.dataset_table,
                role=identity.role,
                department=identity.department,
                clearance=identity.clearance,
                title=request.title,
                ai_state=safe_ai_state,
                conversation_id=request.conversation_id,
                view_id=request.view_id,
                metadata=request.metadata,
            )
        )
    except ViewStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    get_audit_logger().log(
        event_type="sharing",
        action="save_view",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={"view_id": result["view_id"], "version": result["version"]},
    )
    result["share_url"] = result["share_path"]
    return result


@app.get("/views/{view_id}")
async def get_view(
    view_id: str,
    identity: AuthIdentity = Depends(require_permission("views:read")),
) -> dict[str, Any]:
    service = get_view_storage_service()
    try:
        result = service.get_view(view_id)
    except ViewStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    if not can_access_owned_resource(
        identity,
        owner_user_id=result["owner_user_id"],
        owner_project_id=result["owner_project_id"],
    ):
        get_audit_logger().log(
            event_type="authorization",
            action="view_read",
            status="denied",
            severity="ALERT",
            user_id=identity.user_id,
            project_id=identity.project_id,
            detail={"view_id": view_id},
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "RBAC_FORBIDDEN",
                "message": "You do not have permission to access this resource",
            },
        )

    result["ai_state"] = redact_structure(result["ai_state"], role=identity.role)
    result["share_url"] = result["share_path"]
    return result


@app.get("/share/{view_id}")
async def get_shared_view(
    view_id: str,
    identity: AuthIdentity = Depends(require_permission("views:share")),
) -> dict[str, Any]:
    service = get_view_storage_service()
    try:
        result = service.get_view(view_id)
    except ViewStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    result["ai_state"] = redact_structure(result["ai_state"], role=identity.role)
    result["share_url"] = result["share_path"]
    get_audit_logger().log(
        event_type="sharing",
        action="share_view",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={"view_id": view_id, "current_version": result["current_version"]},
    )
    return result


@app.post("/views/{view_id}/rollback/{version}")
async def rollback_view(
    view_id: str,
    version: int,
    request: RollbackViewRequest,
    identity: AuthIdentity = Depends(require_permission("views:rollback")),
) -> dict[str, Any]:
    ensure_scope(identity, user_id=request.user_id, project_id=request.project_id)

    service = get_view_storage_service()
    try:
        result = service.rollback_view(
            view_id,
            RollbackInput(
                user_id=identity.user_id,
                project_id=identity.project_id,
                role=identity.role,
                department=identity.department,
                clearance=identity.clearance,
                target_version=version,
            ),
        )
    except ViewStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc

    get_audit_logger().log(
        event_type="sharing",
        action="rollback_view",
        status="success",
        user_id=identity.user_id,
        project_id=identity.project_id,
        detail={"view_id": view_id, "version": result["version"]},
    )
    result["share_url"] = result["share_path"]
    return result


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


def _build_query_ast(*, request: SemanticQueryRequest, parser: IntentParser) -> SemanticQueryAST:
    explicit_filters = [item.to_query_filter() for item in request.filters]

    if request.metric:
        return SemanticQueryAST(
            metric=request.metric,
            group_by=request.group_by,
            filters=explicit_filters,
            limit=request.limit,
        )

    if request.intent:
        parsed = parser.parse(request.intent)
        merged_group_by = request.group_by or parsed.group_by
        merged_filters = [*parsed.filters, *explicit_filters]
        return SemanticQueryAST(
            metric=parsed.metric,
            group_by=merged_group_by,
            filters=merged_filters,
            limit=request.limit,
        )

    raise MetricCompileError(
        code="MISSING_QUERY_TARGET",
        message="Either metric or intent must be provided",
    )
