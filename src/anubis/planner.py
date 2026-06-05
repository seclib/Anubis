from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import uuid4

from anubis.agents import AgentRegistry
from anubis.orchestrator import Orchestrator
from anubis.types import AgentDescriptor, Task, TaskResult, TaskStatus, utcnow


class PlanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class StepStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Goal:
    kind: str
    objective: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"goal_{uuid4().hex}")

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class StepTemplate:
    id: str
    task_kind: str
    required_capabilities: frozenset[str]
    reason: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    depends_on: frozenset[str] = field(default_factory=frozenset)
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        object.__setattr__(self, "required_capabilities", frozenset(self.required_capabilities))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "depends_on", frozenset(self.depends_on))


@dataclass(frozen=True, slots=True)
class PlanTemplate:
    goal_kind: str
    steps: tuple[StepTemplate, ...]

    def __post_init__(self) -> None:
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step ids must be unique")
        known = set(step_ids)
        for step in self.steps:
            missing = step.depends_on - known
            if missing:
                raise ValueError(f"step {step.id} depends on unknown steps: {sorted(missing)}")


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: str
    task_kind: str
    required_capabilities: frozenset[str]
    reason: str
    payload: Mapping[str, Any]
    depends_on: frozenset[str]
    max_attempts: int
    status: StepStatus = StepStatus.PENDING
    assigned_agent: str | None = None
    task_id: str | None = None
    attempts: int = 0
    last_error: str | None = None
    explanation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_capabilities", frozenset(self.required_capabilities))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "depends_on", frozenset(self.depends_on))


@dataclass(frozen=True, slots=True)
class Plan:
    goal: Goal
    steps: tuple[PlanStep, ...]
    status: PlanStatus = PlanStatus.PENDING
    id: str = field(default_factory=lambda: f"plan_{uuid4().hex}")
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    explanation: tuple[str, ...] = field(default_factory=tuple)

    def step(self, step_id: str) -> PlanStep:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(f"unknown step: {step_id}")


class PlanningEngine:
    """Deterministic, explainable planner for ANUBIS workflows."""

    def __init__(
        self,
        *,
        templates: Sequence[PlanTemplate] | None = None,
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        self._templates = {template.goal_kind: template for template in templates or ()}
        self._agent_registry = agent_registry

    def register_template(self, template: PlanTemplate) -> None:
        if template.goal_kind in self._templates:
            raise ValueError(f"plan template already registered: {template.goal_kind}")
        self._templates[template.goal_kind] = template

    async def create_plan(
        self,
        goal: Goal,
        *,
        agents: Sequence[AgentDescriptor] | None = None,
    ) -> Plan:
        template = self._template_for(goal)
        available_agents = await self._resolve_agents(agents)
        steps = tuple(self._build_step(step, available_agents) for step in template.steps)
        plan = Plan(
            goal=goal,
            steps=steps,
            explanation=(
                f"Selected template '{template.goal_kind}' for goal '{goal.kind}'.",
                f"Decomposed goal into {len(steps)} deterministic step(s).",
            ),
        )
        return self.re_evaluate(plan)

    async def dispatch_ready(self, plan: Plan, orchestrator: Orchestrator) -> Plan:
        next_steps: list[PlanStep] = []
        for step in plan.steps:
            if step.status != StepStatus.READY:
                next_steps.append(step)
                continue
            task = Task(
                kind=step.task_kind,
                payload={
                    **dict(step.payload),
                    "goal_id": plan.goal.id,
                    "plan_id": plan.id,
                    "step_id": step.id,
                },
                required_capabilities=step.required_capabilities,
                metadata={
                    "assigned_agent": step.assigned_agent,
                    "planner_reason": step.reason,
                    "attempt": step.attempts + 1,
                },
            )
            task_id = await orchestrator.submit(task)
            next_steps.append(
                replace(
                    step,
                    status=StepStatus.DISPATCHED,
                    task_id=task_id,
                    attempts=step.attempts + 1,
                    explanation=(
                        f"Dispatched to '{step.assigned_agent}' because it satisfies "
                        f"{sorted(step.required_capabilities)}."
                    ),
                )
            )
        return self.re_evaluate(replace(plan, steps=tuple(next_steps)))

    def apply_result(self, plan: Plan, task_result: TaskResult) -> Plan:
        next_steps: list[PlanStep] = []
        matched = False
        for step in plan.steps:
            if step.task_id != task_result.task_id:
                next_steps.append(step)
                continue

            matched = True
            if task_result.status == TaskStatus.SUCCEEDED:
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.SUCCEEDED,
                        last_error=None,
                        explanation="Marked succeeded from orchestrator task result.",
                    )
                )
            elif step.attempts < step.max_attempts:
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.READY,
                        task_id=None,
                        last_error=task_result.error,
                        explanation=(
                            "Task failed but retry budget remains; step is ready for "
                            "deterministic re-dispatch."
                        ),
                    )
                )
            else:
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.FAILED,
                        last_error=task_result.error,
                        explanation="Task failed and retry budget is exhausted.",
                    )
                )

        if not matched:
            raise KeyError(f"task result does not belong to this plan: {task_result.task_id}")
        return self.re_evaluate(replace(plan, steps=tuple(next_steps)))

    def re_evaluate(self, plan: Plan) -> Plan:
        completed = {step.id for step in plan.steps if step.status == StepStatus.SUCCEEDED}
        failed = {step.id for step in plan.steps if step.status == StepStatus.FAILED}
        next_steps: list[PlanStep] = []

        for step in plan.steps:
            if step.status in {
                StepStatus.DISPATCHED,
                StepStatus.SUCCEEDED,
                StepStatus.FAILED,
                StepStatus.SKIPPED,
            }:
                next_steps.append(step)
                continue

            if step.depends_on & failed:
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.BLOCKED,
                        explanation=(
                            "Blocked because dependency failed: "
                            f"{sorted(step.depends_on & failed)}."
                        ),
                    )
                )
            elif step.assigned_agent is None:
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.BLOCKED,
                        explanation="Blocked because no registered agent can satisfy this step.",
                    )
                )
            elif step.depends_on.issubset(completed):
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.READY,
                        explanation="Ready because all dependencies are satisfied.",
                    )
                )
            else:
                missing = sorted(step.depends_on - completed)
                next_steps.append(
                    replace(
                        step,
                        status=StepStatus.PENDING,
                        explanation=f"Pending dependency completion: {missing}.",
                    )
                )

        statuses = {step.status for step in next_steps}
        if StepStatus.FAILED in statuses or StepStatus.BLOCKED in statuses:
            plan_status = PlanStatus.FAILED
        elif all(step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED} for step in next_steps):
            plan_status = PlanStatus.SUCCEEDED
        elif any(step.status in {StepStatus.READY, StepStatus.DISPATCHED} for step in next_steps):
            plan_status = PlanStatus.RUNNING
        else:
            plan_status = PlanStatus.PENDING

        return replace(plan, steps=tuple(next_steps), status=plan_status, updated_at=utcnow())

    def explain(self, plan: Plan) -> tuple[str, ...]:
        lines = [
            f"Plan {plan.id} for goal {plan.goal.id} is {plan.status}.",
            *plan.explanation,
        ]
        for step in plan.steps:
            agent = step.assigned_agent or "unassigned"
            lines.append(
                f"{step.id}: {step.status}; agent={agent}; "
                f"capabilities={sorted(step.required_capabilities)}; reason={step.reason}; "
                f"state={step.explanation}"
            )
        return tuple(lines)

    def _template_for(self, goal: Goal) -> PlanTemplate:
        try:
            return self._templates[goal.kind]
        except KeyError as exc:
            raise LookupError(f"no plan template registered for goal kind: {goal.kind}") from exc

    async def _resolve_agents(
        self,
        agents: Sequence[AgentDescriptor] | None,
    ) -> tuple[AgentDescriptor, ...]:
        if agents is not None:
            return tuple(sorted(agents, key=lambda agent: agent.name))
        if self._agent_registry is None:
            return ()
        return await self._agent_registry.descriptors()

    def _build_step(
        self,
        template: StepTemplate,
        agents: Sequence[AgentDescriptor],
    ) -> PlanStep:
        assigned_agent, assignment_reason = self._assign_agent(template, agents)
        payload = {**dict(template.payload)}
        return PlanStep(
            id=template.id,
            task_kind=template.task_kind,
            required_capabilities=template.required_capabilities,
            reason=template.reason,
            payload=payload,
            depends_on=template.depends_on,
            max_attempts=template.max_attempts,
            assigned_agent=assigned_agent,
            explanation=assignment_reason,
        )

    def _assign_agent(
        self,
        step: StepTemplate,
        agents: Sequence[AgentDescriptor],
    ) -> tuple[str | None, str]:
        candidates = [
            agent
            for agent in agents
            if step.required_capabilities.issubset(agent.capabilities)
        ]
        if not candidates:
            return (
                None,
                "No registered agent satisfies required capabilities: "
                f"{sorted(step.required_capabilities)}.",
            )

        selected = sorted(
            candidates,
            key=lambda agent: (
                len(agent.capabilities - step.required_capabilities),
                agent.name,
                agent.version,
            ),
        )[0]
        return (
            selected.name,
            f"Assigned to '{selected.name}' by deterministic capability match.",
        )


def default_security_templates() -> tuple[PlanTemplate, ...]:
    return (
        PlanTemplate(
            goal_kind="investigate_alert",
            steps=(
                StepTemplate(
                    id="collect_context",
                    task_kind="collect_context",
                    required_capabilities=frozenset({"telemetry.read"}),
                    reason="Gather local evidence before making any judgment.",
                    max_attempts=2,
                ),
                StepTemplate(
                    id="analyze_evidence",
                    task_kind="analyze_evidence",
                    required_capabilities=frozenset({"reason.plan"}),
                    reason="Convert evidence into hypotheses and next actions.",
                    depends_on=frozenset({"collect_context"}),
                ),
                StepTemplate(
                    id="recommend_response",
                    task_kind="recommend_response",
                    required_capabilities=frozenset({"policy.evaluate"}),
                    reason="Produce a policy-aware response recommendation.",
                    depends_on=frozenset({"analyze_evidence"}),
                ),
            ),
        ),
    )
