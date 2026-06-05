from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


AgentCaller = Callable[[str, str, str], str]


class ToolRunner(Protocol):
    def execute(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class MemoryStore(Protocol):
    def load(self) -> dict[str, Any]:
        ...

    def save(self, memory: dict[str, Any]) -> None:
        ...

    def append_event(self, memory: dict[str, Any], event: dict[str, Any]) -> None:
        ...

    def context_summary(self, memory: dict[str, Any]) -> str:
        ...


def _empty_tool_specs() -> dict[str, Mapping[str, Any]]:
    return {}


def _empty_context(_query: str) -> str:
    return ""


def _empty_query_lookup(_query: str) -> dict[str, Any]:
    return {"enabled": False, "hit": False, "confidence": 0.0, "matches": []}


def _empty_query_store(
    _query: str,
    _result: Any,
    _context: Any,
    _metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"enabled": False, "stored": False}


def _empty_index(_memory: dict[str, Any]) -> dict[str, Any]:
    return {}


def _empty_remember(_task: str, _result: Any, _memory: dict[str, Any]) -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class AgentDependencies:
    tool_executor: ToolRunner
    memory: MemoryStore
    call_agent: AgentCaller
    tool_specs: Callable[[], dict[str, Mapping[str, Any]]] = field(default=_empty_tool_specs)
    vector_context: Callable[[str], str] = field(default=_empty_context)
    hermes_context: Callable[[str], str] = field(default=_empty_context)
    query_cache_lookup: Callable[[str], dict[str, Any]] = field(default=_empty_query_lookup)
    query_cache_store: Callable[[str, Any, Any, dict[str, Any] | None], dict[str, Any]] = field(
        default=_empty_query_store
    )
    index_agent_history: Callable[[dict[str, Any]], dict[str, Any]] = field(default=_empty_index)
    remember_interaction: Callable[[str, Any, dict[str, Any]], dict[str, Any]] = field(
        default=_empty_remember
    )


__all__ = ["AgentCaller", "AgentDependencies", "MemoryStore", "ToolRunner"]
