from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from backend.core.config import settings
from backend.core.paths import ensure_inside
from backend.tools.base import BaseTool, require_string


def resolve_project_path(path: str) -> Path:
    return ensure_inside(settings.project_root.resolve(), Path(path))


class ReadFileTool(BaseTool):
    name = "read_file"

    def run(self, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        path = require_string(tool_input, "path")
        target = resolve_project_path(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return {
            "path": str(target.relative_to(settings.project_root.resolve())),
            "content": target.read_text(encoding="utf-8"),
        }


class WriteFileTool(BaseTool):
    name = "write_file"

    def run(self, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        path = require_string(tool_input, "path")
        content = require_string(tool_input, "content")
        target = resolve_project_path(path)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "path": str(target.relative_to(settings.project_root.resolve())),
            "bytes": len(content.encode("utf-8")),
        }


def read_file(path: str) -> dict[str, Any]:
    return ReadFileTool().invoke({"path": path})


def write_file(path: str, content: str) -> dict[str, Any]:
    return WriteFileTool().invoke({"path": path, "content": content})


__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "read_file",
    "resolve_project_path",
    "write_file",
]
