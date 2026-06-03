from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from anubis.types import JSONObject, JSONSchema, JSONValue, ToolName, ToolResult


@dataclass(frozen=True)
class ToolSpec:
    name: ToolName
    description: str
    input_schema: JSONSchema
    output_schema: JSONSchema


@dataclass
class ToolExecutionContext:
    logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.logs.append(message)


class BaseTool(ABC):
    name: ToolName
    description: str
    input_schema: JSONSchema
    output_schema: JSONSchema

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
        )

    def execute(self, input: JSONObject) -> ToolResult:
        context = ToolExecutionContext()
        output = self.run(input, context)
        return {
            "tool": self.name,
            "input": input,
            "output": output,
            "success": True,
            "error": None,
            "logs": context.logs,
            "duration_ms": 0,
        }

    @abstractmethod
    def run(self, input: JSONObject, context: ToolExecutionContext) -> JSONValue:
        ...


__all__ = ["BaseTool", "ToolExecutionContext", "ToolSpec"]
