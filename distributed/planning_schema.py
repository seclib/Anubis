"""Planning schema for the ANUBIS distributed Planner Agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PlanStepType(StrEnum):
    FILE = "file"
    SHELL = "shell"
    ANALYSIS = "analysis"


@dataclass(frozen=True)
class PlanStep:
    id: str
    action: str
    depends_on: tuple[str, ...]
    type: PlanStepType

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "depends_on": list(self.depends_on),
            "type": self.type.value,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    task_id: str
    steps: tuple[PlanStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "steps": [step.to_dict() for step in self.steps],
        }


__all__ = ["ExecutionPlan", "PlanStep", "PlanStepType"]
