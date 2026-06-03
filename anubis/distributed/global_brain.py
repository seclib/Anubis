"""Strategic autonomous software company brain for ANUBIS DEVIN++."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.autonomous_pipeline import AutonomousPipeline, AutonomousPipelineCycleResult
from anubis.distributed.contracts import AgentType, EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.multi_repo_orchestrator import CrossRepoPlan, MultiRepoOrchestrator
from anubis.distributed.registry import AgentRegistry


class GlobalBrainStage(StrEnum):
    PRIORITIZING = "prioritizing"
    ALLOCATING = "allocating"
    COORDINATING = "coordinating"
    SCHEDULING = "scheduling"
    RUNNING_PIPELINE = "running_pipeline"
    COMPLETED = "completed"
    IDLE = "idle"
    FAILED = "failed"


class BrainTaskKind(StrEnum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MISSING_TESTS = "missing_tests"
    REFACTOR = "refactor"
    INFRA = "infra"


class BrainTaskRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class BrainTask:
    task_id: str
    title: str
    description: str
    kind: BrainTaskKind = BrainTaskKind.FEATURE
    priority: int = 0
    risk: BrainTaskRisk = BrainTaskRisk.LOW
    repo_hints: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "kind": self.kind.value,
            "priority": self.priority,
            "risk": self.risk.value,
            "repo_hints": list(self.repo_hints),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PrioritizedTask:
    task: BrainTask
    score: int
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ResourceAllocation:
    task_id: str
    agent_assignments: dict[str, tuple[str, ...]]
    available_capacity: dict[str, int]
    saturated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_assignments": {agent_type: list(agent_ids) for agent_type, agent_ids in self.agent_assignments.items()},
            "available_capacity": dict(self.available_capacity),
            "saturated": self.saturated,
        }


@dataclass(frozen=True)
class RepoCoordinationPlan:
    task_id: str
    plan: CrossRepoPlan

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "plan": self.plan.to_dict(),
        }


@dataclass(frozen=True)
class ImprovementSchedule:
    cycle_id: str
    scheduled_tasks: tuple[PrioritizedTask, ...]
    allocations: tuple[ResourceAllocation, ...]
    repo_plans: tuple[RepoCoordinationPlan, ...]
    max_parallel: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "scheduled_tasks": [task.to_dict() for task in self.scheduled_tasks],
            "allocations": [allocation.to_dict() for allocation in self.allocations],
            "repo_plans": [plan.to_dict() for plan in self.repo_plans],
            "max_parallel": self.max_parallel,
        }


@dataclass(frozen=True)
class GlobalBrainCycleResult:
    cycle_id: str
    success: bool
    stage: GlobalBrainStage
    prioritized_tasks: tuple[PrioritizedTask, ...] = ()
    allocations: tuple[ResourceAllocation, ...] = ()
    repo_plans: tuple[RepoCoordinationPlan, ...] = ()
    schedule: ImprovementSchedule | None = None
    pipeline_result: AutonomousPipelineCycleResult | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "success": self.success,
            "stage": self.stage.value,
            "prioritized_tasks": [task.to_dict() for task in self.prioritized_tasks],
            "allocations": [allocation.to_dict() for allocation in self.allocations],
            "repo_plans": [plan.to_dict() for plan in self.repo_plans],
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "pipeline_result": self.pipeline_result.to_dict() if self.pipeline_result else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class GlobalBrainConfig:
    max_tasks_per_cycle: int = 3
    max_parallel_tasks: int = 2
    run_pipeline: bool = True
    allow_high_risk: bool = False


class GlobalBrain:
    """Prioritizes, allocates, coordinates, and schedules autonomous company work."""

    KIND_WEIGHT: dict[BrainTaskKind, int] = {
        BrainTaskKind.SECURITY: 60,
        BrainTaskKind.BUGFIX: 50,
        BrainTaskKind.MISSING_TESTS: 40,
        BrainTaskKind.PERFORMANCE: 35,
        BrainTaskKind.INFRA: 30,
        BrainTaskKind.FEATURE: 25,
        BrainTaskKind.REFACTOR: 15,
    }
    RISK_PENALTY: dict[BrainTaskRisk, int] = {
        BrainTaskRisk.LOW: 0,
        BrainTaskRisk.MEDIUM: 15,
        BrainTaskRisk.HIGH: 45,
    }
    REQUIRED_AGENTS: tuple[AgentType, ...] = (AgentType.PLANNER, AgentType.EXECUTOR, AgentType.REVIEWER)

    def __init__(
        self,
        *,
        repo_orchestrator: MultiRepoOrchestrator | None = None,
        agent_registry: AgentRegistry | None = None,
        autonomous_pipeline: AutonomousPipeline | None = None,
        event_bus: EventBus | None = None,
        config: GlobalBrainConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.repo_orchestrator = repo_orchestrator or MultiRepoOrchestrator()
        self.agent_registry = agent_registry or AgentRegistry()
        self.autonomous_pipeline = autonomous_pipeline or AutonomousPipeline(event_bus=self.event_bus)
        self.config = config or GlobalBrainConfig()

    async def run_cycle(self, cycle_id: str, tasks: tuple[BrainTask, ...]) -> GlobalBrainCycleResult:
        try:
            await self._publish(cycle_id, GlobalBrainStage.PRIORITIZING, "Global brain prioritizing tasks")
            prioritized = self.prioritize_tasks(tasks)
            if not prioritized:
                result = GlobalBrainCycleResult(cycle_id=cycle_id, success=True, stage=GlobalBrainStage.IDLE)
                await self._publish(cycle_id, GlobalBrainStage.IDLE, "Global brain found no schedulable tasks", result.to_dict())
                return result

            await self._publish(cycle_id, GlobalBrainStage.ALLOCATING, "Global brain allocating agent resources")
            allocations = self.allocate_resources(prioritized)
            await self._publish(cycle_id, GlobalBrainStage.COORDINATING, "Global brain coordinating repositories")
            repo_plans = self.coordinate_repositories(prioritized)
            await self._publish(cycle_id, GlobalBrainStage.SCHEDULING, "Global brain scheduling improvements")
            schedule = self.schedule_improvements(cycle_id, prioritized, allocations, repo_plans)
            if not schedule.scheduled_tasks:
                result = GlobalBrainCycleResult(
                    cycle_id=cycle_id,
                    success=True,
                    stage=GlobalBrainStage.IDLE,
                    prioritized_tasks=prioritized,
                    allocations=allocations,
                    repo_plans=repo_plans,
                    schedule=schedule,
                )
                await self._publish(cycle_id, GlobalBrainStage.IDLE, "Global brain found no available execution capacity", result.to_dict())
                return result

            pipeline_result = None
            if self.config.run_pipeline:
                await self._publish(cycle_id, GlobalBrainStage.RUNNING_PIPELINE, "Global brain activating autonomous pipeline")
                pipeline_result = self.autonomous_pipeline.run_once(cycle_id)
                if isawaitable(pipeline_result):
                    pipeline_result = await pipeline_result

            success = pipeline_result.success if pipeline_result is not None else True
            stage = GlobalBrainStage.COMPLETED if success else GlobalBrainStage.FAILED
            result = GlobalBrainCycleResult(
                cycle_id=cycle_id,
                success=success,
                stage=stage,
                prioritized_tasks=prioritized,
                allocations=allocations,
                repo_plans=repo_plans,
                schedule=schedule,
                pipeline_result=pipeline_result,
                error=None if success else "autonomous pipeline failed",
            )
            await self._publish(
                cycle_id,
                stage,
                "Global brain cycle completed" if success else "Global brain cycle failed",
                result.to_dict(),
            )
            return result
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            result = GlobalBrainCycleResult(cycle_id=cycle_id, success=False, stage=GlobalBrainStage.FAILED, error=error)
            await self._publish(cycle_id, GlobalBrainStage.FAILED, error, result.to_dict())
            return result

    def run_cycle_sync(self, cycle_id: str, tasks: tuple[BrainTask, ...]) -> GlobalBrainCycleResult:
        return asyncio.run(self.run_cycle(cycle_id, tasks))

    def prioritize_tasks(self, tasks: tuple[BrainTask, ...]) -> tuple[PrioritizedTask, ...]:
        prioritized = [self._prioritize(task) for task in tasks if self._allowed(task)]
        prioritized.sort(key=lambda item: (-item.score, item.task.task_id))
        return tuple(prioritized[: self.config.max_tasks_per_cycle])

    def allocate_resources(self, prioritized_tasks: tuple[PrioritizedTask, ...]) -> tuple[ResourceAllocation, ...]:
        remaining = self._capacity_by_agent()
        allocations: list[ResourceAllocation] = []
        for item in prioritized_tasks:
            assignments: dict[str, list[str]] = defaultdict(list)
            for agent_type in self.REQUIRED_AGENTS:
                for agent in self.agent_registry.available(agent_type):
                    if remaining[agent.agent_id] > 0:
                        assignments[agent_type.value].append(agent.agent_id)
                        remaining[agent.agent_id] -= 1
                        break
            capacity_snapshot = {
                agent_type.value: sum(remaining[agent.agent_id] for agent in self.agent_registry.available(agent_type))
                for agent_type in self.REQUIRED_AGENTS
            }
            saturated = any(not assignments.get(agent_type.value) for agent_type in self.REQUIRED_AGENTS)
            allocations.append(
                ResourceAllocation(
                    task_id=item.task.task_id,
                    agent_assignments={key: tuple(value) for key, value in assignments.items()},
                    available_capacity=capacity_snapshot,
                    saturated=saturated,
                )
            )
        return tuple(allocations)

    def coordinate_repositories(self, prioritized_tasks: tuple[PrioritizedTask, ...]) -> tuple[RepoCoordinationPlan, ...]:
        plans: list[RepoCoordinationPlan] = []
        for item in prioritized_tasks:
            goal = self._repo_goal(item.task)
            plan = self.repo_orchestrator.plan_task(task_id=item.task.task_id, goal=goal)
            plans.append(RepoCoordinationPlan(task_id=item.task.task_id, plan=plan))
        return tuple(plans)

    def schedule_improvements(
        self,
        cycle_id: str,
        prioritized_tasks: tuple[PrioritizedTask, ...],
        allocations: tuple[ResourceAllocation, ...],
        repo_plans: tuple[RepoCoordinationPlan, ...],
    ) -> ImprovementSchedule:
        unsaturated_ids = {allocation.task_id for allocation in allocations if not allocation.saturated}
        scheduled = tuple(task for task in prioritized_tasks if task.task.task_id in unsaturated_ids)
        return ImprovementSchedule(
            cycle_id=cycle_id,
            scheduled_tasks=scheduled[: self.config.max_parallel_tasks],
            allocations=allocations,
            repo_plans=repo_plans,
            max_parallel=self.config.max_parallel_tasks,
        )

    def _prioritize(self, task: BrainTask) -> PrioritizedTask:
        reasons: list[str] = []
        score = task.priority * 10
        if task.priority:
            reasons.append(f"priority:{task.priority}")
        kind_weight = self.KIND_WEIGHT[task.kind]
        score += kind_weight
        reasons.append(f"kind:{task.kind.value}:{kind_weight}")
        risk_penalty = self.RISK_PENALTY[task.risk]
        score -= risk_penalty
        if risk_penalty:
            reasons.append(f"risk_penalty:{task.risk.value}:{risk_penalty}")
        if task.repo_hints:
            score += 5 * len(task.repo_hints)
            reasons.append(f"repo_hints:{len(task.repo_hints)}")
        return PrioritizedTask(task=task, score=max(0, score), reasons=tuple(reasons))

    def _allowed(self, task: BrainTask) -> bool:
        return self.config.allow_high_risk or task.risk != BrainTaskRisk.HIGH

    def _repo_goal(self, task: BrainTask) -> str:
        hints = " ".join(task.repo_hints)
        return f"{task.title} {task.description} {hints}".strip()

    def _capacity_by_agent(self) -> dict[str, int]:
        capacity: dict[str, int] = {}
        for agent in self.agent_registry.list_agents():
            capacity[agent.agent_id] = agent.available_capacity
        return capacity

    async def _publish(
        self,
        cycle_id: str,
        stage: GlobalBrainStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_type = EventType.TASK_FAILED if stage == GlobalBrainStage.FAILED else EventType.TASK_STATE_CHANGED
        published = self.event_bus.publish(
            OrchestrationEvent(
                event_type=event_type,
                task_id=cycle_id,
                message=message,
                payload={"stage": stage.value, **(payload or {})},
            )
        )
        if isawaitable(published):
            await published


__all__ = [
    "BrainTask",
    "BrainTaskKind",
    "BrainTaskRisk",
    "GlobalBrain",
    "GlobalBrainConfig",
    "GlobalBrainCycleResult",
    "GlobalBrainStage",
    "ImprovementSchedule",
    "PrioritizedTask",
    "RepoCoordinationPlan",
    "ResourceAllocation",
]
