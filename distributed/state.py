"""Execution state manager for distributed orchestration."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock
from typing import Any

from anubis.distributed.contracts import (
    AgentAssignment,
    AgentResult,
    AgentType,
    Subtask,
    TaskEnvelope,
    TaskStatus,
    new_id,
    utc_now,
)


class ExecutionStateManager:
    """In-memory lifecycle store for tasks and subtasks.

    This is intentionally storage-agnostic. A durable implementation can use the
    same method boundaries later.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskEnvelope] = {}
        self._assignments: dict[str, AgentAssignment] = {}
        self._lock = RLock()

    def create_task(
        self,
        objective: str,
        *,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 2,
    ) -> TaskEnvelope:
        task_id = new_id("task")
        planner_id = new_id("subtask")
        executor_id = new_id("subtask")
        reviewer_id = new_id("subtask")
        subtasks = (
            Subtask(
                task_id=task_id,
                subtask_id=planner_id,
                agent_type=AgentType.PLANNER,
                objective=f"Decompose and plan: {objective}",
                max_retries=max_retries,
            ),
            Subtask(
                task_id=task_id,
                subtask_id=executor_id,
                agent_type=AgentType.EXECUTOR,
                objective=f"Execute the approved plan for: {objective}",
                dependencies=(planner_id,),
                max_retries=max_retries,
            ),
            Subtask(
                task_id=task_id,
                subtask_id=reviewer_id,
                agent_type=AgentType.REVIEWER,
                objective=f"Review and validate the execution result for: {objective}",
                dependencies=(executor_id,),
                max_retries=max_retries,
            ),
        )
        task = TaskEnvelope(
            task_id=task_id,
            objective=objective,
            subtasks=subtasks,
            metadata=metadata or {},
        )
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> TaskEnvelope:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        return task

    def get_assignment(self, assignment_id: str) -> AgentAssignment:
        with self._lock:
            assignment = self._assignments.get(assignment_id)
        if assignment is None:
            raise KeyError(f"Unknown assignment: {assignment_id}")
        return assignment

    def ready_subtasks(self, task_id: str) -> tuple[Subtask, ...]:
        task = self.get_task(task_id)
        completed = {
            subtask.subtask_id
            for subtask in task.subtasks
            if subtask.status == TaskStatus.COMPLETED
        }
        return tuple(
            subtask
            for subtask in task.subtasks
            if subtask.status == TaskStatus.CREATED
            and all(dependency in completed for dependency in subtask.dependencies)
        )

    def assign_subtask(self, assignment: AgentAssignment) -> Subtask:
        with self._lock:
            task = self._tasks.get(assignment.task_id)
            if task is None:
                raise KeyError(f"Unknown task: {assignment.task_id}")

            updated_subtasks: list[Subtask] = []
            assigned: Subtask | None = None
            for subtask in task.subtasks:
                if subtask.subtask_id == assignment.subtask_id:
                    assigned = replace(
                        subtask,
                        status=TaskStatus.ASSIGNED,
                        assigned_agent_id=assignment.agent_id,
                        assignment_id=assignment.assignment_id,
                        attempts=subtask.attempts + 1,
                        updated_at=utc_now(),
                    )
                    updated_subtasks.append(assigned)
                else:
                    updated_subtasks.append(subtask)

            if assigned is None:
                raise KeyError(f"Unknown subtask: {assignment.subtask_id}")

            self._assignments[assignment.assignment_id] = assignment
            self._tasks[assignment.task_id] = replace(
                task,
                status=TaskStatus.ASSIGNED,
                subtasks=tuple(updated_subtasks),
                updated_at=utc_now(),
            )
            return assigned

    def complete_assignment(self, result: AgentResult) -> Subtask:
        assignment = self.get_assignment(result.assignment_id)
        new_status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED

        with self._lock:
            task = self._tasks[assignment.task_id]
            updated_subtasks: list[Subtask] = []
            completed_subtask: Subtask | None = None

            for subtask in task.subtasks:
                if subtask.subtask_id == assignment.subtask_id:
                    completed_subtask = replace(
                        subtask,
                        status=new_status,
                        result=result.output if result.success else subtask.result,
                        error=result.error if not result.success else None,
                        updated_at=utc_now(),
                    )
                    updated_subtasks.append(completed_subtask)
                else:
                    updated_subtasks.append(subtask)

            if completed_subtask is None:
                raise KeyError(f"Unknown subtask: {assignment.subtask_id}")

            updated_task = replace(
                task,
                subtasks=tuple(updated_subtasks),
                updated_at=utc_now(),
            )
            self._tasks[assignment.task_id] = self._derive_task_status(updated_task)
            return completed_subtask

    def reset_for_retry(self, subtask_id: str, task_id: str) -> Subtask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Unknown task: {task_id}")

            updated_subtasks: list[Subtask] = []
            reset_subtask: Subtask | None = None
            for subtask in task.subtasks:
                if subtask.subtask_id == subtask_id:
                    if subtask.attempts > subtask.max_retries:
                        raise RuntimeError(f"Retry limit exceeded for subtask: {subtask_id}")
                    reset_subtask = replace(
                        subtask,
                        status=TaskStatus.CREATED,
                        assigned_agent_id=None,
                        assignment_id=None,
                        updated_at=utc_now(),
                    )
                    updated_subtasks.append(reset_subtask)
                else:
                    updated_subtasks.append(subtask)

            if reset_subtask is None:
                raise KeyError(f"Unknown subtask: {subtask_id}")

            self._tasks[task_id] = replace(
                task,
                status=TaskStatus.ASSIGNED,
                subtasks=tuple(updated_subtasks),
                updated_at=utc_now(),
            )
            return reset_subtask

    def fail_task(self, task_id: str, error: str) -> TaskEnvelope:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Unknown task: {task_id}")
            updated = replace(task, status=TaskStatus.FAILED, error=error, updated_at=utc_now())
            self._tasks[task_id] = updated
            return updated

    def aggregate_task_result(self, task_id: str) -> TaskEnvelope:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Unknown task: {task_id}")
            result = {
                "task_id": task.task_id,
                "objective": task.objective,
                "subtasks": [
                    {
                        "subtask_id": subtask.subtask_id,
                        "agent_type": subtask.agent_type.value,
                        "attempts": subtask.attempts,
                        "result": subtask.result,
                    }
                    for subtask in task.subtasks
                ],
            }
            updated = replace(task, status=TaskStatus.COMPLETED, result=result, updated_at=utc_now())
            self._tasks[task_id] = updated
            return updated

    def _derive_task_status(self, task: TaskEnvelope) -> TaskEnvelope:
        statuses = {subtask.status for subtask in task.subtasks}
        if TaskStatus.FAILED in statuses:
            return replace(task, status=TaskStatus.FAILED)
        if statuses == {TaskStatus.COMPLETED}:
            return replace(task, status=TaskStatus.COMPLETED)
        if TaskStatus.ASSIGNED in statuses or TaskStatus.COMPLETED in statuses:
            return replace(task, status=TaskStatus.RUNNING)
        return task


__all__ = ["ExecutionStateManager"]
