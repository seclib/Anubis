from __future__ import annotations

from typing import Protocol

from anubis.types import JSONObject, TaskId, TaskSnapshot, TaskStatus


class TaskManager(Protocol):
    def create(self, goal: str, context: JSONObject) -> TaskSnapshot:
        ...

    def update_status(self, task_id: TaskId, status: TaskStatus) -> TaskSnapshot:
        ...

    def update_context(self, task_id: TaskId, context: JSONObject) -> TaskSnapshot:
        ...

    def update_plan(self, task_id: TaskId, plan: JSONObject) -> TaskSnapshot:
        ...

    def log_history(self, task_id: TaskId, event: str, payload: JSONObject) -> TaskSnapshot:
        ...

    def get(self, task_id: TaskId) -> TaskSnapshot:
        ...


__all__ = ["TaskManager"]
