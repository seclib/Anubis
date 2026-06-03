from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from backend.core.config import settings
from backend.core.paths import ensure_inside


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


ALLOWED_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.RUNNING},
    TaskStatus.RUNNING: {TaskStatus.DONE, TaskStatus.FAILED},
    TaskStatus.DONE: set(),
    TaskStatus.FAILED: set(),
}


@dataclass(frozen=True)
class TaskHistoryEvent:
    timestamp: str
    event: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask:
    id: str
    goal: str
    status: TaskStatus
    context: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    history: list[TaskHistoryEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class TaskManager:
    def __init__(self, storage_dir: Path | None = None) -> None:
        raw_storage_dir = storage_dir or Path("state/tasks")
        self.storage_dir = ensure_inside(settings.project_root.resolve(), raw_storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, AgentTask] = {}

    def create_task(self, goal: str, context: Mapping[str, Any] | None = None) -> AgentTask:
        task = AgentTask(
            id=uuid4().hex,
            goal=goal,
            status=TaskStatus.PENDING,
            context=_normalize(context or {}),
        )
        task.history.append(_event("created", {"goal": goal, "context": task.context}))
        self._tasks[task.id] = task
        self._save(task)
        return task

    def get_task(self, task_id: str) -> AgentTask:
        if task_id not in self._tasks:
            self._tasks[task_id] = self._load(task_id)
        return self._tasks[task_id]

    def update_status(self, task_id: str, status: TaskStatus | str, reason: str = "") -> AgentTask:
        task = self.get_task(task_id)
        next_status = TaskStatus(status)
        allowed = ALLOWED_TRANSITIONS[task.status]
        if next_status not in allowed:
            raise ValueError(f"invalid task transition: {task.status.value} -> {next_status.value}")
        task.status = next_status
        self._touch(task)
        task.history.append(_event("status_changed", {"status": next_status.value, "reason": reason}))
        self._save(task)
        return task

    def start_task(self, task_id: str) -> AgentTask:
        return self.update_status(task_id, TaskStatus.RUNNING, "agent loop started")

    def complete_task(self, task_id: str, reason: str = "") -> AgentTask:
        return self.update_status(task_id, TaskStatus.DONE, reason)

    def fail_task(self, task_id: str, reason: str = "") -> AgentTask:
        return self.update_status(task_id, TaskStatus.FAILED, reason)

    def update_context(self, task_id: str, context: Mapping[str, Any]) -> AgentTask:
        task = self.get_task(task_id)
        task.context = _normalize(context)
        self._touch(task)
        task.history.append(_event("context_updated", task.context))
        self._save(task)
        return task

    def update_plan(self, task_id: str, plan: Mapping[str, Any]) -> AgentTask:
        task = self.get_task(task_id)
        task.plan = _normalize(plan)
        self._touch(task)
        task.history.append(_event("plan_updated", task.plan))
        self._save(task)
        return task

    def log_action(self, task_id: str, event: str, payload: Mapping[str, Any] | None = None) -> AgentTask:
        task = self.get_task(task_id)
        task.history.append(_event(event, _normalize(payload or {})))
        self._touch(task)
        self._save(task)
        return task

    def replay(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        return [asdict(event) for event in task.history]

    def snapshot(self, task_id: str) -> dict[str, Any]:
        return self.get_task(task_id).to_dict()

    def _path(self, task_id: str) -> Path:
        return ensure_inside(self.storage_dir, Path(f"{task_id}.json"))

    def _save(self, task: AgentTask) -> None:
        self._path(task.id).write_text(json.dumps(task.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _load(self, task_id: str) -> AgentTask:
        path = self._path(task_id)
        if not path.exists():
            raise KeyError(f"unknown task: {task_id}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        history = [
            TaskHistoryEvent(
                timestamp=str(item.get("timestamp", "")),
                event=str(item.get("event", "")),
                payload=dict(item.get("payload") or {}),
            )
            for item in raw.get("history", [])
            if isinstance(item, Mapping)
        ]
        return AgentTask(
            id=str(raw["id"]),
            goal=str(raw["goal"]),
            status=TaskStatus(str(raw["status"])),
            context=dict(raw.get("context") or {}),
            plan=dict(raw.get("plan") or {}),
            history=history,
            created_at=str(raw.get("created_at") or _now()),
            updated_at=str(raw.get("updated_at") or _now()),
        )

    def _touch(self, task: AgentTask) -> None:
        task.updated_at = _now()


def _event(event: str, payload: Mapping[str, Any] | None = None) -> TaskHistoryEvent:
    return TaskHistoryEvent(timestamp=_now(), event=event, payload=_normalize(payload or {}))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, TaskStatus):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


__all__ = [
    "AgentTask",
    "TaskHistoryEvent",
    "TaskManager",
    "TaskStatus",
]
