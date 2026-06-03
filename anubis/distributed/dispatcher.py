"""Task dispatcher for routing subtasks to registered agent workers."""

from __future__ import annotations

from anubis.distributed.contracts import AgentAssignment, Subtask, new_id
from anubis.distributed.registry import AgentRegistry


class TaskDispatcher:
    """Selects a worker for a subtask without executing the subtask."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def dispatch(self, subtask: Subtask, context: dict | None = None) -> AgentAssignment:
        candidates = self.registry.available(subtask.agent_type)
        if not candidates:
            raise RuntimeError(f"No available agent for type: {subtask.agent_type}")

        selected = min(
            candidates,
            key=lambda agent: (agent.active_assignments, -agent.available_capacity, agent.agent_id),
        )
        acquired = self.registry.acquire(selected.agent_id)
        return AgentAssignment(
            assignment_id=new_id("assignment"),
            task_id=subtask.task_id,
            subtask_id=subtask.subtask_id,
            agent_id=acquired.agent_id,
            agent_type=acquired.agent_type,
            objective=subtask.objective,
            context=context or {},
        )


__all__ = ["TaskDispatcher"]
