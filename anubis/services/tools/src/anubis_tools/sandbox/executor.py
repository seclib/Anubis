from __future__ import annotations

import asyncio
from time import perf_counter

from anubis_tools.core.registry import ToolRegistry
from anubis_tools.sandbox.schemas import SecureToolExecutionRequest, ToolPermission


class SandboxExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContainerBoundarySandboxExecutor:
    """Executes tools inside the already-hardened tool-runner container boundary."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, request: SecureToolExecutionRequest, permission: ToolPermission) -> tuple[dict, float]:
        started_at = perf_counter()
        if permission.shell:
            raise SandboxExecutionError("SHELL_DENIED", "Shell execution is forbidden")
        try:
            result = await asyncio.wait_for(
                self._registry.execute(request.tool_name, request.parameters),
                timeout=permission.timeout_seconds,
            )
        except TimeoutError as exc:
            raise SandboxExecutionError("TIMEOUT", "Tool execution timed out") from exc
        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        if result.status == "failed":
            raise SandboxExecutionError("TOOL_FAILED", result.error or "Tool execution failed")
        return result.output, duration_ms
