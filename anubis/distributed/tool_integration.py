"""Tool integration boundary for the distributed Executor Agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from anubis.distributed.execution_errors import ToolNotAllowedError


ALLOWED_EXECUTOR_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "search_codebase",
        "run_command",
        "git_diff",
        "git_commit",
    }
)

ToolRunner = Callable[[str, Mapping[str, Any] | None], dict[str, Any]]


class ToolIntegrationLayer:
    """Executes only allowlisted tools through an injected tool runner."""

    def __init__(
        self,
        runner: ToolRunner | None = None,
        *,
        allowed_tools: set[str] | frozenset[str] = ALLOWED_EXECUTOR_TOOLS,
    ) -> None:
        self.runner = runner or self._default_runner
        self.allowed_tools = frozenset(allowed_tools)

    def execute(self, tool: str, tool_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if tool not in self.allowed_tools:
            raise ToolNotAllowedError(f"Tool is not allowed for executor agent: {tool}")
        result = self.runner(tool, dict(tool_input or {}))
        if not isinstance(result, dict):
            return {
                "tool": tool,
                "input": dict(tool_input or {}),
                "output": result,
                "success": False,
                "logs": [f"Invalid tool result type: {type(result).__name__}"],
            }
        return result

    def _default_runner(self, tool: str, tool_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
        from backend.tools.registry import invoke_tool

        return invoke_tool(tool, tool_input)


__all__ = ["ALLOWED_EXECUTOR_TOOLS", "ToolIntegrationLayer", "ToolRunner"]
