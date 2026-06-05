from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Tool(Protocol):
    def execute(self, input: dict) -> dict:
        ...


@dataclass(frozen=True)
class ToolRoute:
    tool_name: str
    action: str | None = None


class ToolRouter:
    def __init__(self, tools: dict[str, Tool] | None = None) -> None:
        self.tools = tools or default_tools()

    def register(self, name: str, tool: Tool) -> None:
        self.tools[_clean(name)] = tool

    def route(self, tool_name: str, payload: dict) -> dict:
        route = self._resolve(tool_name, payload)
        tool = self.tools.get(route.tool_name)
        routed_payload = dict(payload)
        if route.action is not None:
            routed_payload.setdefault("action", route.action)

        if tool is None:
            return format_tool_result(
                tool_name,
                payload,
                {
                    "ok": False,
                    "error": f"unknown tool: {tool_name}",
                },
            )

        try:
            result = tool.execute(routed_payload)
        except Exception as exc:
            result = {
                "ok": False,
                "error": str(exc),
                "type": exc.__class__.__name__,
            }
        return format_tool_result(tool_name, payload, result)

    def _resolve(self, tool_name: str, payload: dict) -> ToolRoute:
        name = _clean(tool_name)
        if "." in name:
            tool, action = name.split(".", 1)
            return ToolRoute(tool, action)

        if name in {"read_file", "write_file", "list_directory"}:
            return ToolRoute("filesystem", name)
        if name in {"create_repo", "list_issues", "commit"}:
            return ToolRoute("github", name)
        if name in {"search", "fetch"}:
            return ToolRoute("web", name)

        action = payload.get("action")
        return ToolRoute(name, str(action) if action else None)


def route_tool(tool_name: str, payload: dict) -> dict:
    return default_tool_router().route(tool_name, payload)


def default_tool_router() -> ToolRouter:
    return ToolRouter()


def default_tools() -> dict[str, Tool]:
    from anubis.tools.filesystem_tool import FilesystemTool
    from anubis.tools.github_tool import GitHubTool
    from anubis.tools.web_tool import WebTool

    return {
        "filesystem": FilesystemTool(),
        "github": GitHubTool(),
        "web": WebTool(),
    }


def format_tool_result(tool_name: str, payload: dict, result: dict) -> dict:
    return {
        "TOOL": tool_name,
        "INPUT": payload,
        "RESULT": result,
    }


def _clean(value: str) -> str:
    return value.strip().lower().replace("-", "_")


__all__ = [
    "Tool",
    "ToolRoute",
    "ToolRouter",
    "default_tool_router",
    "default_tools",
    "format_tool_result",
    "route_tool",
]
