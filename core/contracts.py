"""Shared dependency-injection contracts.

These protocols are intentionally below agent/runtime/tools/memory/llm so every
layer can type its dependencies without importing a concrete implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Protocol


class MemoryStore(Protocol):
    def load(self) -> dict[str, Any]: ...
    def save(self, memory: dict[str, Any]) -> None: ...
    def append_event(self, memory: dict[str, Any], event: dict[str, Any]) -> None: ...
    def context_summary(self, memory: dict[str, Any]) -> str: ...


class ToolRunner(Protocol):
    def execute(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]: ...


AgentCaller = Callable[[str, str, str], str]
AgentPromptBuilder = Callable[[str, str, str], str]
AgentSpecGetter = Callable[[str], Any]


@dataclass(frozen=True)
class AgentDependencies:
    """All runtime services consumed by the autonomous agent loop."""

    tool_executor: ToolRunner
    memory: MemoryStore
    call_agent: AgentCaller
    tool_specs: Callable[[], Mapping[str, Any]] = lambda: {}
    vector_context: Callable[[str], str] = lambda query: "Vector context unavailable."
    hermes_context: Callable[[str], str] = lambda query: "Hermes memory unavailable."
    index_agent_history: Callable[[dict[str, Any]], dict[str, Any]] = lambda memory: {}
    remember_interaction: Callable[[str, Any, dict[str, Any]], dict[str, Any]] = (
        lambda task, result, memory: {}
    )


__all__ = [
    "AgentCaller",
    "AgentDependencies",
    "AgentPromptBuilder",
    "AgentSpecGetter",
    "MemoryStore",
    "ToolRunner",
]
