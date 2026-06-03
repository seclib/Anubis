from __future__ import annotations

from typing import Protocol

from anubis.types import AgentContext, ContextChunk, TaskSnapshot


class ContextProvider(Protocol):
    def get_context(self, task: TaskSnapshot) -> AgentContext:
        ...


class TaskContextProvider:
    def get_context(self, task: TaskSnapshot) -> AgentContext:
        raw_context = task.get("context", {})
        compressed = str(raw_context.get("compressed", ""))
        return AgentContext(
            task_id=task["id"],
            goal=task["goal"],
            chunks=(),
            compressed=compressed,
            metadata={"source": "task.context"},
        )


__all__ = ["ContextProvider", "TaskContextProvider"]
