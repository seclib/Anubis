"""Pure reasoning Planner Agent for ANUBIS Phase B2."""

from __future__ import annotations

import re
from dataclasses import dataclass

from anubis.distributed.dependency_resolver import DependencyResolver
from anubis.distributed.planning_schema import ExecutionPlan, PlanStep, PlanStepType


_ACTION_WORDS = {
    "add",
    "build",
    "change",
    "create",
    "design",
    "fix",
    "implement",
    "refactor",
    "remove",
    "update",
    "validate",
}


@dataclass(frozen=True)
class PlannerAgent:
    """Builds structured plans without executing tools or reading files."""

    dependency_resolver: DependencyResolver = DependencyResolver()

    def plan(self, task_id: str, task: str) -> ExecutionPlan:
        objective = self._normalize_text(task)
        if not task_id.strip():
            raise ValueError("task_id is required")
        if not objective:
            raise ValueError("task must not be empty")

        work_items = self._work_items(objective)
        steps: list[PlanStep] = [
            PlanStep(
                id="step_001",
                action=f"Analyze objective and constraints for: {objective}",
                depends_on=(),
                type=PlanStepType.ANALYSIS,
            )
        ]

        implementation_ids: list[str] = []
        for index, item in enumerate(work_items, start=2):
            step_id = f"step_{index:03d}"
            implementation_ids.append(step_id)
            steps.append(
                PlanStep(
                    id=step_id,
                    action=self._implementation_action(item),
                    depends_on=("step_001",),
                    type=self._step_type(item),
                )
            )

        validation_id = f"step_{len(steps) + 1:03d}"
        steps.append(
            PlanStep(
                id=validation_id,
                action="Run focused validation for all completed implementation steps",
                depends_on=tuple(implementation_ids),
                type=PlanStepType.SHELL,
            )
        )

        final_id = f"step_{len(steps) + 1:03d}"
        steps.append(
            PlanStep(
                id=final_id,
                action="Review validation results and prepare structured execution summary",
                depends_on=(validation_id,),
                type=PlanStepType.ANALYSIS,
            )
        )

        plan = ExecutionPlan(task_id=task_id.strip(), steps=tuple(steps))
        return self.dependency_resolver.validate(plan)

    def plan_dict(self, task_id: str, task: str) -> dict:
        return self.plan(task_id, task).to_dict()

    def _work_items(self, objective: str) -> tuple[str, ...]:
        parts = [
            self._normalize_text(part)
            for part in re.split(r"\s+(?:and|then|plus)\s+|[,;]\s*", objective)
        ]
        candidates = tuple(part for part in parts if self._is_work_item(part))
        return candidates or (objective,)

    def _is_work_item(self, text: str) -> bool:
        words = set(re.findall(r"[a-zA-Z]+", text.lower()))
        return bool(words & _ACTION_WORDS) or len(text.split()) >= 3

    def _implementation_action(self, item: str) -> str:
        if self._step_type(item) == PlanStepType.ANALYSIS:
            return f"Reason through and specify expected outcome for: {item}"
        return f"Apply minimal implementation change for: {item}"

    def _step_type(self, item: str) -> PlanStepType:
        lowered = item.lower()
        if any(word in lowered for word in ("test", "command", "shell", "run ", "validate")):
            return PlanStepType.SHELL
        if any(word in lowered for word in ("analyze", "plan", "review", "inspect", "design")):
            return PlanStepType.ANALYSIS
        return PlanStepType.FILE

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


__all__ = ["PlannerAgent"]
