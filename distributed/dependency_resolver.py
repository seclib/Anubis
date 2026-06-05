"""Dependency validation and grouping for planner output."""

from __future__ import annotations

from collections import deque

from anubis.distributed.planning_schema import ExecutionPlan, PlanStep


class DependencyResolutionError(ValueError):
    """Raised when a plan has invalid dependency structure."""


class DependencyResolver:
    """Validates dependencies and exposes parallel execution groups."""

    def validate(self, plan: ExecutionPlan) -> ExecutionPlan:
        ids = [step.id for step in plan.steps]
        if len(ids) != len(set(ids)):
            raise DependencyResolutionError("Plan step ids must be unique")

        known_ids = set(ids)
        for step in plan.steps:
            if step.id in step.depends_on:
                raise DependencyResolutionError(f"Step cannot depend on itself: {step.id}")
            missing = [dependency for dependency in step.depends_on if dependency not in known_ids]
            if missing:
                raise DependencyResolutionError(
                    f"Step {step.id} depends on unknown steps: {', '.join(missing)}"
                )

        self.topological_steps(plan)
        return plan

    def topological_steps(self, plan: ExecutionPlan) -> tuple[PlanStep, ...]:
        by_id = {step.id: step for step in plan.steps}
        dependents: dict[str, list[str]] = {step.id: [] for step in plan.steps}
        indegree: dict[str, int] = {step.id: len(step.depends_on) for step in plan.steps}

        for step in plan.steps:
            for dependency in step.depends_on:
                if dependency not in dependents:
                    raise DependencyResolutionError(
                        f"Step {step.id} depends on unknown step: {dependency}"
                    )
                dependents[dependency].append(step.id)

        ready = deque(step.id for step in plan.steps if indegree[step.id] == 0)
        ordered: list[PlanStep] = []

        while ready:
            step_id = ready.popleft()
            ordered.append(by_id[step_id])
            for dependent_id in dependents[step_id]:
                indegree[dependent_id] -= 1
                if indegree[dependent_id] == 0:
                    ready.append(dependent_id)

        if len(ordered) != len(plan.steps):
            raise DependencyResolutionError("Plan dependencies contain a cycle")
        return tuple(ordered)

    def parallel_groups(self, plan: ExecutionPlan) -> tuple[tuple[PlanStep, ...], ...]:
        self.validate(plan)
        remaining = {step.id: step for step in plan.steps}
        completed: set[str] = set()
        groups: list[tuple[PlanStep, ...]] = []

        while remaining:
            ready = tuple(
                step
                for step in plan.steps
                if step.id in remaining and all(dependency in completed for dependency in step.depends_on)
            )
            if not ready:
                raise DependencyResolutionError("Plan dependencies contain a cycle")
            groups.append(ready)
            for step in ready:
                completed.add(step.id)
                remaining.pop(step.id)

        return tuple(groups)


__all__ = ["DependencyResolutionError", "DependencyResolver"]
