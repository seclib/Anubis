"""Generic tool execution utilities.

The executor is deliberately independent from concrete tools. Runtime wiring
injects the registry of callable tools.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Mapping, Protocol

logger = logging.getLogger(__name__)

ToolFunction = Callable[..., Any]


class ToolAudit(Protocol):
    def __call__(
        self,
        event: str,
        tool: str,
        *,
        args: Mapping[str, Any] | None = None,
        success: bool | None = None,
        result: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None: ...


class ToolRegistryReloader(Protocol):
    def __call__(self) -> Mapping[str, ToolFunction]: ...


def _noop_audit(
    event: str,
    tool: str,
    *,
    args: Mapping[str, Any] | None = None,
    success: bool | None = None,
    result: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    return None


class ToolExecutor:
    """Execute an injected registry of tools and normalize all results."""

    def __init__(
        self,
        tools: Mapping[str, ToolFunction],
        *,
        audit: ToolAudit | None = None,
        dynamic_loader: ToolRegistryReloader | None = None,
        sandbox_error: type[Exception] | tuple[type[Exception], ...] = (),
        dynamic_tool_error: type[Exception] | tuple[type[Exception], ...] = (),
    ) -> None:
        self.tools: dict[str, ToolFunction] = dict(tools)
        self._audit = audit or _noop_audit
        self._dynamic_loader = dynamic_loader
        self._sandbox_error = sandbox_error
        self._dynamic_tool_error = dynamic_tool_error
        self._dynamic_tools_loaded = False

    def refresh_dynamic_tools(self) -> dict[str, ToolFunction]:
        if self._dynamic_loader is None:
            return {}
        dynamic_tools = dict(self._dynamic_loader())
        self.tools.update(dynamic_tools)
        return dynamic_tools

    def _ensure_dynamic_tools_loaded(self) -> None:
        if not self._dynamic_tools_loaded:
            self.refresh_dynamic_tools()
            self._dynamic_tools_loaded = True

    def execute(self, tool: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_dynamic_tools_loaded()
        if tool not in self.tools:
            result = {
                "success": False,
                "output": (
                    f"Unknown tool: {tool}. If this capability is missing, use "
                    "`create_dynamic_tool` to generate a reusable Python tool in tools/generated/."
                ),
            }
            self._audit("denied", tool, args=args, success=False, result=result)
            return result

        if args is None:
            args = {}
        elif not isinstance(args, Mapping):
            result = {
                "success": False,
                "output": f"Invalid args for {tool}: expected a mapping, got {type(args).__name__}",
            }
            self._audit("denied", tool, args={}, success=False, result=result)
            return result

        normalized_args = dict(args)
        self._audit("start", tool, args=normalized_args)
        try:
            output = self.tools[tool](**normalized_args)
            if tool == "create_dynamic_tool":
                self.refresh_dynamic_tools()
            result = {"success": True, "output": output}
            self._audit("success", tool, args=normalized_args, success=True, result=result)
            return result
        except self._sandbox_error as exc:
            result = {
                "success": False,
                "output": {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                    "sandbox": True,
                },
            }
            self._audit("denied", tool, args=normalized_args, success=False, error=str(exc))
            logger.warning("Sandbox denied tool '%s': %s", tool, exc)
            return result
        except self._dynamic_tool_error as exc:
            result = {
                "success": False,
                "output": {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                    "dynamic_tool": True,
                },
            }
            self._audit("denied", tool, args=normalized_args, success=False, error=str(exc))
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
            self._audit("failure", tool, args=normalized_args, success=False, error=str(exc))
            return result

__all__ = [
    "ToolAudit",
    "ToolExecutor",
    "ToolFunction",
    "ToolRegistryReloader",
]
