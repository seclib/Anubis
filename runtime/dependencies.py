"""Concrete dependency wiring for the default Anubis runtime."""

from __future__ import annotations

from typing import Any

from core.contracts import AgentCaller, AgentDependencies
from memory import state as runtime_memory
from memory import vector as vector_memory
from memory import hermes as hermes_memory
from runtime.tool_registry import default_tool_executor, runtime_tool_specs


class RuntimeMemoryStore:
    """Adapter around memory.state used by CLI and API runtimes."""

    def load(self) -> dict[str, Any]:
        return runtime_memory.load_memory()

    def save(self, memory: dict[str, Any]) -> None:
        runtime_memory.save_memory(memory)

    def append_event(self, memory: dict[str, Any], event: dict[str, Any]) -> None:
        runtime_memory.append_event(memory, event)

    def context_summary(self, memory: dict[str, Any]) -> str:
        return runtime_memory.get_context_summary(memory)


def default_agent_dependencies(call_agent: AgentCaller) -> AgentDependencies:
    return AgentDependencies(
        tool_executor=default_tool_executor(),
        memory=RuntimeMemoryStore(),
        call_agent=call_agent,
        tool_specs=runtime_tool_specs,
        vector_context=lambda query: vector_memory.retrieve_context(query=query, top_k=5),
        hermes_context=hermes_memory.hermes_context_text,
        index_agent_history=vector_memory.index_agent_history,
        remember_interaction=hermes_memory.remember_interaction,
    )


__all__ = ["RuntimeMemoryStore", "default_agent_dependencies"]
