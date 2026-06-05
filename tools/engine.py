from __future__ import annotations

from time import perf_counter
import traceback

from anubis.tools.errors import ToolError
from anubis.tools.interfaces import Tool
from anubis.tools.logging import ToolCallLogger
from anubis.tools.registry import ToolRegistry
from anubis.tools.validation import validate_input
from anubis.types import JSONObject, ToolName, ToolResult


class ToolExecutionEngine:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        logger: ToolCallLogger | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.logger = logger or ToolCallLogger()

    def register(self, tool: Tool) -> None:
        self.registry.register(tool)

    def discover(self) -> list[Tool]:
        return self.registry.discover()

    def execute(self, name: ToolName, input: JSONObject) -> ToolResult:
        started = perf_counter()
        logs: list[str] = []
        try:
            tool = self.registry.get(name)
            validate_input(tool.input_schema, input)
            result = tool.execute(input)
            logs.extend(result.get("logs", []))
            result = {
                **result,
                "duration_ms": _duration_ms(started),
                "logs": logs,
            }
        except Exception as exc:
            logs.append(f"{exc.__class__.__name__}: {exc}")
            result = {
                "tool": name,
                "input": input,
                "output": {
                    "type": exc.__class__.__name__,
                    "traceback": traceback.format_exc(),
                    "retry_safe": isinstance(exc, ToolError),
                },
                "success": False,
                "error": str(exc),
                "logs": logs,
                "duration_ms": _duration_ms(started),
            }
        self.logger.log(result)
        return result


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


__all__ = ["ToolExecutionEngine"]
