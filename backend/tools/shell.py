from __future__ import annotations

from typing import Any, Mapping

from backend.tools.base import BaseTool, require_string
from backend.tools.sandbox import SandboxExecutor, ToolRequest


class RunCommandTool(BaseTool):
    name = "run_command"

    def __init__(self, executor: SandboxExecutor | None = None) -> None:
        self.executor = executor or SandboxExecutor()

    def run(self, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        cmd = require_string(tool_input, "cmd")
        result = self.executor.execute(
            ToolRequest(
                command=cmd,
                justification="run_command tool invocation",
                cwd=str(tool_input.get("cwd", ".")),
                allow_network=bool(tool_input.get("allow_network", False)),
            )
        )
        return {
            "cmd": cmd,
            "code": result.code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
        }

    def succeeded(self, output: Any) -> bool:
        return (
            isinstance(output, dict)
            and output.get("code") == 0
            and output.get("timed_out") is False
        )


def run_command(cmd: str) -> dict[str, Any]:
    return RunCommandTool().invoke({"cmd": cmd})


__all__ = ["RunCommandTool", "run_command"]
