"""Transform raw input into executable task objects."""

from anubis.planner import Goal
from anubis.types import Task


class TaskDigestion:
    def digest(self, kind: str, payload: dict | None = None) -> Task:
        return Task(kind=kind, payload=payload or {})

    def digest_goal(self, goal: Goal) -> Task:
        return self.digest(
            goal.kind,
            {
                "objective": goal.objective,
                **dict(goal.payload),
            },
        )
