from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolResult:
    tool: str
    input: dict[str, Any]
    output: Any
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseTool(ABC):
    name: str

    def __call__(self, **tool_input: Any) -> dict[str, Any]:
        return self.invoke(tool_input)

    def invoke(self, tool_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
        input_data = dict(tool_input or {})
        try:
            output = self.run(input_data)
            return ToolResult(
                tool=self.name,
                input=input_data,
                output=output,
                success=self.succeeded(output),
            ).to_dict()
        except Exception as exc:
            return ToolResult(
                tool=self.name,
                input=input_data,
                output={
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                },
                success=False,
            ).to_dict()

    @abstractmethod
    def run(self, tool_input: Mapping[str, Any]) -> Any:
        raise NotImplementedError

    def succeeded(self, output: Any) -> bool:
        return True


def require_string(tool_input: Mapping[str, Any], key: str) -> str:
    value = tool_input.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


__all__ = ["BaseTool", "ToolResult", "require_string"]
