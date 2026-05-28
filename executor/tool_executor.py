"""Tool execution utilities."""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Mapping

from tools.filesystem import list_files, read_file, write_file
from tools.repo import (
    detect_project_type,
    find_entrypoints,
    find_file,
    get_file_tree,
    scan_repo_tree,
    search_code,
)
from tools.terminal import run_command

logger = logging.getLogger(__name__)

ToolFunction = Callable[..., Any]

TOOLS: dict[str, ToolFunction] = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "run_command": run_command,
    "search_code": search_code,
    "scan_repo_tree": scan_repo_tree,
    "detect_project_type": detect_project_type,
    "find_entrypoints": find_entrypoints,
    "find_file": find_file,
    "get_file_tree": get_file_tree,
}


def execute_tool(tool: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Execute a tool and return a normalized result payload."""
    if tool not in TOOLS:
        return {"success": False, "output": f"Unknown tool: {tool}"}

    if args is None:
        args = {}
    elif not isinstance(args, Mapping):
        return {
            "success": False,
            "output": f"Invalid args for {tool}: expected a mapping, got {type(args).__name__}",
        }

    try:
        result = TOOLS[tool](**dict(args))
        return {"success": True, "output": result}
    except Exception as exc:
        logger.exception("Error while executing tool '%s'", tool)
        return {
            "success": False,
            "output": {
                "error": str(exc),
                "type": exc.__class__.__name__,
                "traceback": traceback.format_exc(),
            },
        }


__all__ = ["TOOLS", "execute_tool"]
