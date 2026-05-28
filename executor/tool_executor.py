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
from tools.sandbox import SandboxViolation, audit_tool_action
from tools.terminal import run_command
from tools.vector_memory import (
    index_repository,
    retrieve_context,
    semantic_search,
)

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
    "index_repository": index_repository,
    "semantic_search": semantic_search,
    "retrieve_context": retrieve_context,
}


def execute_tool(tool: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Execute a tool and return a normalized result payload."""
    if tool not in TOOLS:
        result = {"success": False, "output": f"Unknown tool: {tool}"}
        audit_tool_action("denied", tool, args=args, success=False, result=result)
        return result

    if args is None:
        args = {}
    elif not isinstance(args, Mapping):
        result = {
            "success": False,
            "output": f"Invalid args for {tool}: expected a mapping, got {type(args).__name__}",
        }
        audit_tool_action("denied", tool, args={}, success=False, result=result)
        return result

    normalized_args = dict(args)
    audit_tool_action("start", tool, args=normalized_args)
    try:
        output = TOOLS[tool](**normalized_args)
        result = {"success": True, "output": output}
        audit_tool_action("success", tool, args=normalized_args, success=True, result=result)
        return result
    except SandboxViolation as exc:
        result = {
            "success": False,
            "output": {
                "error": str(exc),
                "type": exc.__class__.__name__,
                "sandbox": True,
            },
        }
        audit_tool_action("denied", tool, args=normalized_args, success=False, error=str(exc))
        logger.warning("Sandbox denied tool '%s': %s", tool, exc)
        return result
    except Exception as exc:
        logger.exception("Error while executing tool '%s'", tool)
        result = {
            "success": False,
            "output": {
                "error": str(exc),
                "type": exc.__class__.__name__,
                "traceback": traceback.format_exc(),
            },
        }
        audit_tool_action("failure", tool, args=normalized_args, success=False, error=str(exc))
        return result


__all__ = ["TOOLS", "execute_tool"]
