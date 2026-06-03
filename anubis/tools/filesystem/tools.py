from __future__ import annotations

from pathlib import Path

from anubis.tools.base import BaseTool, ToolExecutionContext
from anubis.tools.errors import ToolValidationError
from anubis.types import JSONObject, JSONSchema, JSONValue


PROJECT_ROOT = Path.cwd().resolve()


def resolve_path(path: str, root: Path = PROJECT_ROOT) -> Path:
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ToolValidationError(f"path escapes project root: {path}")
    return candidate


PATH_INPUT_SCHEMA: JSONSchema = {
    "type": "object",
    "required": ["path"],
    "additionalProperties": False,
    "properties": {
        "path": {"type": "string", "description": "Project-relative file path"},
    },
}


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a UTF-8 text file from the current project."
    input_schema = PATH_INPUT_SCHEMA
    output_schema: JSONSchema = {
        "type": "object",
        "required": ["path", "content"],
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
    }

    def run(self, input: JSONObject, context: ToolExecutionContext) -> JSONValue:
        path = str(input["path"])
        target = resolve_path(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        context.log(f"read file {path}")
        return {
            "path": str(target.relative_to(PROJECT_ROOT)),
            "content": target.read_text(encoding="utf-8"),
        }


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write UTF-8 text content to a project file."
    input_schema: JSONSchema = {
        "type": "object",
        "required": ["path", "content"],
        "additionalProperties": False,
        "properties": {
            "path": {"type": "string", "description": "Project-relative file path"},
            "content": {"type": "string", "description": "File content"},
        },
    }
    output_schema: JSONSchema = {
        "type": "object",
        "required": ["path", "bytes"],
        "properties": {
            "path": {"type": "string"},
            "bytes": {"type": "integer"},
        },
    }

    def run(self, input: JSONObject, context: ToolExecutionContext) -> JSONValue:
        path = str(input["path"])
        content = str(input["content"])
        target = resolve_path(path)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        context.log(f"wrote file {path}")
        return {
            "path": str(target.relative_to(PROJECT_ROOT)),
            "bytes": len(content.encode("utf-8")),
        }


def filesystem_tools() -> list[BaseTool]:
    return [ReadFileTool(), WriteFileTool()]


__all__ = ["ReadFileTool", "WriteFileTool", "filesystem_tools", "resolve_path"]
