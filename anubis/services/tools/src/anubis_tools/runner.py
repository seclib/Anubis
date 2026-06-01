from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import Depends, FastAPI, Request
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from anubis_tools.core.registry import ToolRegistry, create_default_registry
from anubis_tools.core.schemas import ToolDefinition, ToolExecutionRequest
from anubis_tools.sandbox.audit import ImmutableAuditLogger
from anubis_tools.sandbox.executor import ContainerBoundarySandboxExecutor
from anubis_tools.sandbox.permissions import PermissionRegistry
from anubis_tools.sandbox.pipeline import SecureToolExecutionPipeline
from anubis_tools.sandbox.sanitizer import OutputSanitizer
from anubis_tools.sandbox.schemas import SecureToolExecutionRequest, SecureToolExecutionResult
from anubis_tools.sandbox.validator import ToolSchemaValidator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANUBIS_", env_file=".env", extra="ignore")

    allowed_workspace: Path = Path("/workspace/sandbox")
    audit_log_path: Path = Path("/var/log/anubis/tool-audit.jsonl")
    log_level: str = "INFO"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.settings = settings
    registry = create_default_registry(workspace_root=str(settings.allowed_workspace))
    permissions = PermissionRegistry(settings.allowed_workspace)
    app.state.registry = registry
    app.state.secure_pipeline = SecureToolExecutionPipeline(
        validator=ToolSchemaValidator(registry=registry, permissions=permissions),
        executor=ContainerBoundarySandboxExecutor(registry),
        sanitizer=OutputSanitizer(),
        audit_logger=ImmutableAuditLogger(settings.audit_log_path),
    )
    yield


def get_registry(request: Request) -> ToolRegistry:
    return request.app.state.registry


def get_secure_pipeline(request: Request) -> SecureToolExecutionPipeline:
    return request.app.state.secure_pipeline


def create_app() -> FastAPI:
    app = FastAPI(title="Anubis Tool Runner", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "tool-runner"}

    @app.get("/v1/tools", response_model=list[ToolDefinition])
    async def list_tools(registry: ToolRegistry = Depends(get_registry)) -> list[ToolDefinition]:
        return registry.list()

    @app.post("/v1/tools/execute", response_model=SecureToolExecutionResult)
    async def execute_tool(
        payload: ToolExecutionRequest,
        request: Request,
        pipeline: SecureToolExecutionPipeline = Depends(get_secure_pipeline),
    ) -> SecureToolExecutionResult:
        secure_request = SecureToolExecutionRequest(
            tool_name=payload.tool_name,
            parameters=payload.arguments,
            request_id=request.state.request_id,
        )
        return await pipeline.execute(secure_request)

    @app.post("/v1/tools/secure-execute", response_model=SecureToolExecutionResult)
    async def secure_execute_tool(
        payload: SecureToolExecutionRequest,
        pipeline: SecureToolExecutionPipeline = Depends(get_secure_pipeline),
    ) -> SecureToolExecutionResult:
        return await pipeline.execute(payload)

    return app
