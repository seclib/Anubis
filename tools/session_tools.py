from __future__ import annotations

import subprocess
from pathlib import Path

from anubis.tools.base import BaseTool, ToolExecutionContext
from anubis.tools.errors import ToolValidationError
from anubis.tools.filesystem.tools import PROJECT_ROOT, resolve_path
from anubis.types import JSONObject, JSONSchema, JSONValue


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and directories under a project-relative path."
    input_schema: JSONSchema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "max_entries": {"type": "integer"},
        },
    }
    output_schema: JSONSchema = {"type": "object"}

    def run(self, input: JSONObject, context: ToolExecutionContext) -> JSONValue:
        path = str(input.get("path") or ".")
        max_entries = int(input.get("max_entries") or 200)
        target = resolve_path(path)
        if not target.exists():
            raise FileNotFoundError(path)
        if target.is_file():
            entries = [target]
        else:
            entries = sorted(target.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))[:max_entries]
        context.log(f"listed {path}")
        return {
            "path": str(target.relative_to(PROJECT_ROOT)),
            "entries": [
                {
                    "name": item.name,
                    "path": str(item.relative_to(PROJECT_ROOT)),
                    "type": "file" if item.is_file() else "dir",
                }
                for item in entries
            ],
        }


class RunShellTool(BaseTool):
    name = "run_shell"
    description = "Run a shell command from the project root with timeout and captured output."
    input_schema: JSONSchema = {
        "type": "object",
        "required": ["cmd"],
        "additionalProperties": False,
        "properties": {
            "cmd": {"type": "string"},
            "timeout": {"type": "integer"},
        },
    }
    output_schema: JSONSchema = {"type": "object"}

    def run(self, input: JSONObject, context: ToolExecutionContext) -> JSONValue:
        cmd = str(input["cmd"]).strip()
        if not cmd:
            raise ToolValidationError("cmd is required")
        if _looks_destructive(cmd):
            raise ToolValidationError(f"destructive shell command blocked: {cmd}")
        timeout = max(1, min(int(input.get("timeout") or 30), 120))
        completed = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        context.log(f"ran shell command: {cmd}")
        return {
            "cmd": cmd,
            "code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }


def _looks_destructive(cmd: str) -> bool:
    normalized = f" {cmd.lower()} "
    blocked = (" rm -rf ", " sudo ", " mkfs", " shutdown", " reboot", " git reset --hard ")
    return any(pattern in normalized for pattern in blocked)


def session_tools() -> list[BaseTool]:
    from anubis.tools.filesystem import ReadFileTool, WriteFileTool

    return [ReadFileTool(), WriteFileTool(), ListFilesTool(), RunShellTool()]


__all__ = ["ListFilesTool", "RunShellTool", "session_tools"]
