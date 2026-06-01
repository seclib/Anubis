from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class FunctionSandbox:
    async def execute(
        self,
        *,
        tool_name: str,
        parameters: dict[str, Any],
        executor: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        safe_parameters = self._copy_safe(parameters)
        result = await asyncio.wait_for(executor(safe_parameters), timeout=timeout_seconds)
        return self._sanitize(result)

    def _copy_safe(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in parameters.items() if not str(key).startswith("_")}

    def _sanitize(self, output: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in output.items():
            if key.lower() in {"token", "secret", "password", "api_key"}:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 8000:
                sanitized[key] = value[:8000]
            else:
                sanitized[key] = value
        return sanitized
