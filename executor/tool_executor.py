"""Tool execution utilities."""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Mapping

from tools.autonomous_developer import (
    create_project_scaffold,
    developer_autonomy_plan,
    developer_project_status,
    install_project_dependencies,
    run_project_build,
    run_project_tests,
    start_project_server,
    stop_project_server,
)
from tools.dynamic_tools import (
    DynamicToolError,
    create_dynamic_tool,
    list_dynamic_tools,
    load_dynamic_tools,
)
from tools.filesystem import list_files, read_file, write_file
from tools.git_autonomy import (
    autonomous_git_commit,
    generate_commit_message,
    git_status,
    rollback_last_autonomous_commit,
    run_git_validations,
)
from tools.hermes_memory import (
    index_obsidian_vault,
    search_hermes_memory,
    store_hermes_memory,
    write_obsidian_note,
)
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
    "git_status": git_status,
    "generate_commit_message": generate_commit_message,
    "run_git_validations": run_git_validations,
    "autonomous_git_commit": autonomous_git_commit,
    "rollback_last_autonomous_commit": rollback_last_autonomous_commit,
    "create_dynamic_tool": create_dynamic_tool,
    "list_dynamic_tools": list_dynamic_tools,
    "developer_project_status": developer_project_status,
    "developer_autonomy_plan": developer_autonomy_plan,
    "create_project_scaffold": create_project_scaffold,
    "install_project_dependencies": install_project_dependencies,
    "run_project_build": run_project_build,
    "run_project_tests": run_project_tests,
    "start_project_server": start_project_server,
    "stop_project_server": stop_project_server,
    "search_hermes_memory": search_hermes_memory,
    "index_obsidian_vault": index_obsidian_vault,
    "store_hermes_memory": store_hermes_memory,
    "write_obsidian_note": write_obsidian_note,
}


def refresh_dynamic_tools() -> dict[str, ToolFunction]:
    """Load generated tools from disk into the executable registry."""
    dynamic_tools = load_dynamic_tools()
    TOOLS.update(dynamic_tools)
    return dynamic_tools


def execute_tool(tool: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Execute a tool and return a normalized result payload."""
    refresh_dynamic_tools()
    if tool not in TOOLS:
        result = {
            "success": False,
            "output": (
                f"Unknown tool: {tool}. If this capability is missing, use "
                "`create_dynamic_tool` to generate a reusable Python tool in tools/generated/."
            ),
        }
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
        if tool == "create_dynamic_tool":
            refresh_dynamic_tools()
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
    except DynamicToolError as exc:
        result = {
            "success": False,
            "output": {
                "error": str(exc),
                "type": exc.__class__.__name__,
                "dynamic_tool": True,
            },
        }
        audit_tool_action("denied", tool, args=normalized_args, success=False, error=str(exc))
        logger.warning("Dynamic tool denied for '%s': %s", tool, exc)
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


__all__ = ["TOOLS", "execute_tool", "refresh_dynamic_tools"]
