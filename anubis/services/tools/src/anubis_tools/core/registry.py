from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from anubis_tools.builtins.file_reader import FileReaderTool
from anubis_tools.builtins.memory_retriever import MemoryRetrieverTool
from anubis_tools.builtins.note_writer import NoteWriterTool
from anubis_tools.builtins.web_search import WebSearchTool
from anubis_tools.core.schemas import ToolDefinition, ToolExecutionResult

ToolExecutor = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class RegisteredTool:
    def __init__(self, definition: ToolDefinition, executor: ToolExecutor) -> None:
        self.definition = definition
        self.executor = executor


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, definition: ToolDefinition, executor: ToolExecutor) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = RegisteredTool(definition, executor)

    def list(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolExecutionResult(tool_name=tool_name, status="failed", error="Tool is not registered")
        try:
            output = await asyncio.wait_for(tool.executor(arguments), timeout=tool.definition.timeout_seconds)
            return ToolExecutionResult(tool_name=tool_name, status="succeeded", output=output)
        except (ValidationError, ValueError) as exc:
            return ToolExecutionResult(tool_name=tool_name, status="failed", error=str(exc))
        except TimeoutError:
            return ToolExecutionResult(tool_name=tool_name, status="failed", error="Tool execution timed out")
        except Exception as exc:  # noqa: BLE001 - boundary catches tool failures by design.
            return ToolExecutionResult(tool_name=tool_name, status="failed", error=f"Tool failed: {exc}")


def create_default_registry(*, workspace_root: str = ".") -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        WebSearchTool(),
        FileReaderTool(workspace_root=workspace_root),
        NoteWriterTool(workspace_root=workspace_root),
        MemoryRetrieverTool(),
    ):
        registry.register(tool.definition, tool.execute)
    return registry
