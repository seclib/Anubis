from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from anubis_tools.sandbox.aliases import canonical_tool_name
from anubis_tools.sandbox.audit import ImmutableAuditLogger
from anubis_tools.sandbox.executor import ContainerBoundarySandboxExecutor, SandboxExecutionError
from anubis_tools.sandbox.permissions import PermissionDenied
from anubis_tools.sandbox.sanitizer import OutputSanitizer
from anubis_tools.sandbox.schemas import SecureToolError, SecureToolExecutionRequest, SecureToolExecutionResult
from anubis_tools.sandbox.validator import ToolSchemaValidator, ToolValidationError


class SecureToolExecutionPipeline:
    def __init__(
        self,
        *,
        validator: ToolSchemaValidator,
        executor: ContainerBoundarySandboxExecutor,
        sanitizer: OutputSanitizer,
        audit_logger: ImmutableAuditLogger,
    ) -> None:
        self._validator = validator
        self._executor = executor
        self._sanitizer = sanitizer
        self._audit_logger = audit_logger

    async def execute(self, request: SecureToolExecutionRequest) -> SecureToolExecutionResult:
        if not request.request_id:
            request = request.model_copy(update={"request_id": str(uuid4())})
        original_tool_name = request.tool_name
        request = request.model_copy(update={"tool_name": canonical_tool_name(request.tool_name)})
        started_at = perf_counter()
        try:
            validated, permission = self._validator.validate(request)
            output, duration_ms = await self._executor.execute(validated, permission)
            sanitized_output = self._sanitizer.sanitize(output)
            output_hash = self._sanitizer.output_hash(sanitized_output)
            await self._audit_logger.append(
                request_id=request.request_id,
                tool_name=request.tool_name,
                parameters=self._sanitizer.sanitize(request.parameters),
                status="succeeded",
                duration_ms=duration_ms,
                output_hash=output_hash,
                error_code=None,
            )
            return SecureToolExecutionResult(
                tool_name=original_tool_name,
                request_id=request.request_id,
                status="succeeded",
                output=sanitized_output,
            )
        except (ToolValidationError, PermissionDenied, SandboxExecutionError) as exc:
            code = getattr(exc, "code", "TOOL_ERROR")
            return await self._fail(request, display_tool_name=original_tool_name, code=code, message=str(exc), started_at=started_at)
        except Exception:
            return await self._fail(
                request,
                display_tool_name=original_tool_name,
                code="SANDBOX_INTERNAL_ERROR",
                message="Tool execution failed safely",
                started_at=started_at,
            )

    async def _fail(
        self,
        request: SecureToolExecutionRequest,
        *,
        display_tool_name: str | None = None,
        code: str,
        message: str,
        started_at: float,
    ) -> SecureToolExecutionResult:
        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        error = SecureToolError(code=code, message=message, request_id=request.request_id)
        output = {"error": error.model_dump(mode="json")}
        await self._audit_logger.append(
            request_id=request.request_id,
            tool_name=request.tool_name,
            parameters=self._sanitizer.sanitize(request.parameters),
            status="denied" if code in {"UNKNOWN_TOOL", "PATH_DENIED", "SHELL_DENIED"} else "failed",
            duration_ms=duration_ms,
            output_hash=self._sanitizer.output_hash(output),
            error_code=code,
        )
        return SecureToolExecutionResult(
            tool_name=display_tool_name or request.tool_name,
            request_id=request.request_id,
            status="failed",
            error=error,
        )
