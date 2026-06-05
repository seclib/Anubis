from __future__ import annotations

from collections.abc import Iterable

from anubis.tools.errors import ToolNotFoundError
from anubis.tools.interfaces import Tool
from anubis.types import JSONObject, ToolName, ToolResult


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] | None = None) -> None:
        self._tools: dict[ToolName, Tool] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("tool name is required")
        self._tools[tool.name] = tool

    def get(self, name: ToolName) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"unknown tool: {name}") from exc

    def discover(self) -> list[Tool]:
        return [self._tools[name] for name in sorted(self._tools)]

    def execute(self, name: ToolName, input: JSONObject) -> ToolResult:
        return self.get(name).execute(input)


__all__ = ["ToolRegistry"]
