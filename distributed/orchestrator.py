"""Central orchestration engine for ANUBIS Phase B1.

The orchestrator coordinates distributed agents. It never executes tools and it
does not perform repository or filesystem I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anubis.distributed.contracts import (
    AgentAssignment,
    AgentRegistration,
    AgentResult,
    EventType,
    OrchestrationEvent,
    Subtask,
    TaskEnvelope,
    TaskStatus,
)
from anubis.distributed.dispatcher import TaskDispatcher
from anubis.distributed.events import InMemoryEventBus
from anubis.distributed.registry import AgentRegistry
from anubis.distributed.state import ExecutionStateManager


@dataclass(frozen=True)
class OrchestrationReceipt:
    task: TaskEnvelope
    assignments: tuple[AgentAssignment, ...]


class DistributedOrchestrator:
    """Coordinates planner, executor, and reviewer workers."""

    def __init__(
        self,
        *,
        registry: AgentRegistry | None = None,
        dispatcher: TaskDispatcher | None = None,
        event_bus: InMemoryEventBus | None = None,
        state: ExecutionStateManager | None = None,
        max_retries: int = 2,
    ) -> None:
        self.registry = registry or AgentRegistry()
        self.dispatcher = dispatcher or TaskDispatcher(self.registry)
        self.event_bus = event_bus or InMemoryEventBus()
        self.state = state or ExecutionStateManager()
        self.max_retries = max_retries

    def register_agent(self, registration: AgentRegistration) -> AgentRegistration:
        return self.registry.register(registration)

    def receive_task(
        self,
        objective: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> OrchestrationReceipt:
        task = self.state.create_task(
            objective,
            metadata=metadata,
            max_retries=self.max_retries,
        )
        self._emit(
            EventType.TASK_CREATED,
            task.task_id,
            "Task created",
            payload={"objective": objective, "metadata": metadata or {}},
        )
        assignments = self._dispatch_ready(task.task_id)
        return OrchestrationReceipt(task=self.state.get_task(task.task_id), assignments=assignments)

    def complete_assignment(self, result: AgentResult) -> OrchestrationReceipt:
        assignment = self.state.get_assignment(result.assignment_id)
        self.registry.release(assignment.agent_id)
        subtask = self.state.complete_assignment(result)

        if result.success:
            self._emit(
                EventType.TASK_COMPLETED,
                assignment.task_id,
                "Subtask completed",
                subtask_id=assignment.subtask_id,
                assignment_id=assignment.assignment_id,
                agent_id=assignment.agent_id,
                payload={"agent_type": assignment.agent_type.value, "output": result.output},
            )
            task = self.state.get_task(assignment.task_id)
            if all(item.status == TaskStatus.COMPLETED for item in task.subtasks):
                task = self.state.aggregate_task_result(task.task_id)
                self._emit(
                    EventType.TASK_COMPLETED,
                    task.task_id,
                    "Task completed",
                    payload={"result": task.result or {}},
                )
                return OrchestrationReceipt(task=task, assignments=())

            assignments = self._dispatch_ready(assignment.task_id)
            return OrchestrationReceipt(
                task=self.state.get_task(assignment.task_id),
                assignments=assignments,
            )

        if subtask.attempts <= subtask.max_retries:
            self._emit(
                EventType.TASK_FAILED,
                assignment.task_id,
                "Subtask failed; retry scheduled",
                subtask_id=assignment.subtask_id,
                assignment_id=assignment.assignment_id,
                agent_id=assignment.agent_id,
                payload={
                    "agent_type": assignment.agent_type.value,
                    "attempts": subtask.attempts,
                    "max_retries": subtask.max_retries,
                    "error": result.error,
                    "retrying": True,
                },
            )
            self.state.reset_for_retry(subtask.subtask_id, subtask.task_id)
            assignments = self._dispatch_ready(subtask.task_id)
            return OrchestrationReceipt(task=self.state.get_task(subtask.task_id), assignments=assignments)

        task = self.state.fail_task(
            assignment.task_id,
            result.error or "Subtask failed after retry limit",
        )
        self._emit(
            EventType.TASK_FAILED,
            task.task_id,
            "Task failed",
            subtask_id=assignment.subtask_id,
            assignment_id=assignment.assignment_id,
            agent_id=assignment.agent_id,
            payload={
                "agent_type": assignment.agent_type.value,
                "attempts": subtask.attempts,
                "max_retries": subtask.max_retries,
                "error": task.error,
                "retrying": False,
            },
        )
        return OrchestrationReceipt(task=task, assignments=())

    def task_snapshot(self, task_id: str) -> TaskEnvelope:
        return self.state.get_task(task_id)

    def _dispatch_ready(self, task_id: str) -> tuple[AgentAssignment, ...]:
        assignments: list[AgentAssignment] = []
        for subtask in self.state.ready_subtasks(task_id):
            assignment = self._dispatch_subtask(subtask)
            if assignment is not None:
                assignments.append(assignment)
        return tuple(assignments)

    def _dispatch_subtask(self, subtask: Subtask) -> AgentAssignment | None:
        try:
            assignment = self.dispatcher.dispatch(subtask, context=self._assignment_context(subtask))
        except RuntimeError as exc:
            self._emit(
                EventType.TASK_FAILED,
                subtask.task_id,
                "Subtask could not be assigned",
                subtask_id=subtask.subtask_id,
                payload={
                    "agent_type": subtask.agent_type.value,
                    "error": str(exc),
                    "retrying": False,
                },
            )
            return None

        self.state.assign_subtask(assignment)
        self._emit(
            EventType.TASK_ASSIGNED,
            assignment.task_id,
            "Subtask assigned",
            subtask_id=assignment.subtask_id,
            assignment_id=assignment.assignment_id,
            agent_id=assignment.agent_id,
            payload={
                "agent_type": assignment.agent_type.value,
                "objective": assignment.objective,
            },
        )
        return assignment

    def _assignment_context(self, subtask: Subtask) -> dict[str, Any]:
        task = self.state.get_task(subtask.task_id)
        dependency_results = {
            item.subtask_id: item.result
            for item in task.subtasks
            if item.subtask_id in subtask.dependencies and item.result is not None
        }
        return {
            "task_id": task.task_id,
            "objective": task.objective,
            "metadata": dict(task.metadata),
            "dependencies": tuple(subtask.dependencies),
            "dependency_results": dependency_results,
        }

    def _emit(
        self,
        event_type: EventType,
        task_id: str,
        message: str,
        *,
        subtask_id: str | None = None,
        assignment_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> OrchestrationEvent:
        return self.event_bus.emit(
            OrchestrationEvent(
                event_type=event_type,
                task_id=task_id,
                subtask_id=subtask_id,
                assignment_id=assignment_id,
                agent_id=agent_id,
                message=message,
                payload=payload or {},
            )
        )


__all__ = ["DistributedOrchestrator", "OrchestrationReceipt"]
