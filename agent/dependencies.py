"""Dependency wiring for the autonomous agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from executor.tool_executor import ToolExecutor, create_default_tools
from memory import state as runtime_memory


class MemoryStore(Protocol):
    def load(self) -> dict[str, Any]: ...
    def save(self, memory: dict[str, Any]) -> None: ...
    def append_event(self, memory: dict[str, Any], event: dict[str, Any]) -> None: ...
    def context_summary(self, memory: dict[str, Any]) -> str: ...


class ToolRunner(Protocol):
    def execute(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]: ...


class RuntimeMemoryStore:
    """Adapter around memory.state used by the default CLI runtime."""

    def load(self) -> dict[str, Any]:
        return runtime_memory.load_memory()

    def save(self, memory: dict[str, Any]) -> None:
        runtime_memory.save_memory(memory)

    def append_event(self, memory: dict[str, Any], event: dict[str, Any]) -> None:
        runtime_memory.append_event(memory, event)

    def context_summary(self, memory: dict[str, Any]) -> str:
        return runtime_memory.get_context_summary(memory)


@dataclass(frozen=True)
class AgentDependencies:
    """All runtime services needed by the agent loop."""

    tool_executor: ToolRunner
    memory: MemoryStore
    call_agent: Callable[[str, str, str], str]


def default_agent_dependencies() -> AgentDependencies:
    from agent.multi_agent import call_agent

    return AgentDependencies(
        tool_executor=ToolExecutor(create_default_tools()),
        memory=RuntimeMemoryStore(),
        call_agent=call_agent,
    )
