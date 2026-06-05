from __future__ import annotations

from typing import Protocol

from anubis.types import JSONObject, JSONSchema, ToolName, ToolResult


class Tool(Protocol):
    name: ToolName
    description: str
    input_schema: JSONSchema
    output_schema: JSONSchema

    def execute(self, input: JSONObject) -> ToolResult:
        ...


class ToolRegistry(Protocol):
    def register(self, tool: Tool) -> None:
        ...

    def get(self, name: ToolName) -> Tool:
        ...

    def discover(self) -> list[Tool]:
        ...

    def execute(self, name: ToolName, input: JSONObject) -> ToolResult:
        ...


__all__ = ["Tool", "ToolRegistry"]
