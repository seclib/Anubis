"""Master autonomous company runtime for ANUBIS Level 3."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.contracts import AgentType, EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.feature_engine import AutonomousFeatureGenerationEngine, FeatureEngineResult, FeatureRequest
from anubis.distributed.git_agent import GitAgent, GitAutonomyRequest, GitAutonomyResult
from anubis.distributed.improvement_engine import ContinuousImprovementEngine, ImprovementTask
from anubis.distributed.multi_repo_orchestrator import CrossRepoPlan, MultiRepoOrchestrator, RepositoryMetadata
from anubis.distributed.pr_generator import AutonomousPRGenerator, PRGenerationRequest, PRGenerationResult
from anubis.distributed.self_reviewer import SelfReviewEngine, SelfReviewRequest, SelfReviewResult
from anubis.distributed.task_graph import TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class CompanyRuntimeStage(StrEnum):
    DETECTING = "detecting"
    PLANNING = "planning"
    ASSIGNING = "assigning"
    EXECUTING = "executing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    PR_GENERATING = "pr_generating"
    DEPLOY_VALIDATING = "deploy_validating"
    COMPLETED = "completed"
    FAILED = "failed"
    IDLE = "idle"


@dataclass(frozen=True)
class CompanyTask:
    task_id: str
    requirement: str
    repo: RepositoryMetadata | None = None
    improvement_task: ImprovementTask | None = None
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.requirement,
            "repo": self.repo.to_dict() if self.repo else None,
            "improvement_task": self.improvement_task.to_dict() if self.improvement_task else None,
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CompanyAssignment:
    task_id: str
    agent_type: AgentType | str
    objective: str
    stage: CompanyRuntimeStage

    def to_dict(self) -> dict[str, Any]:
        agent_type = self.agent_type.value if hasattr(self.agent_type, "value") else str(self.agent_type)
        return {
            "task_id": self.task_id,
            "agent_type": agent_type,
            "objective": self.objective,
            "stage": self.stage.value,
        }


@dataclass(frozen=True)
class DeployValidationResult:
    success: bool
    checks: tuple[dict[str, Any], ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "checks": [dict(check) for check in self.checks],
            "error": self.error,
        }


@dataclass(frozen=True)
class CompanyTaskResult:
    task: CompanyTask
    success: bool
    plan: CrossRepoPlan | None = None
    assignments: tuple[CompanyAssignment, ...] = ()
    feature_result: FeatureEngineResult | None = None
    git_result: GitAutonomyResult | None = None
    self_review_result: SelfReviewResult | None = None
    pr_result: PRGenerationResult | None = None
    deploy_validation: DeployValidationResult | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "success": self.success,
            "plan": self.plan.to_dict() if self.plan else None,
            "assignments": [assignment.to_dict() for assignment in self.assignments],
            "feature_result": self.feature_result.to_dict() if self.feature_result else None,
            "git_result": self.git_result.to_dict() if self.git_result else None,
            "self_review_result": self.self_review_result.to_dict() if self.self_review_result else None,
            "pr_result": self.pr_result.to_dict() if self.pr_result else None,
            "deploy_validation": self.deploy_validation.to_dict() if self.deploy_validation else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class CompanyCycleResult:
    cycle_id: str
    success: bool
    stage: CompanyRuntimeStage
    detected_tasks: tuple[CompanyTask, ...] = ()
    task_results: tuple[CompanyTaskResult, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "success": self.success,
            "stage": self.stage.value,
            "detected_tasks": [task.to_dict() for task in self.detected_tasks],
            "task_results": [result.to_dict() for result in self.task_results],
            "error": self.error,
        }


@dataclass(frozen=True)
class CompanyRuntimeConfig:
    cycle_interval_seconds: float = 60.0
    max_tasks_per_cycle: int = 3
    deploy_validation_commands: tuple[str, ...] = ("python -m compileall .",)


TaskSource = Callable[[], tuple[CompanyTask, ...] | Awaitable[tuple[CompanyTask, ...]]]


class AutonomousCompanyRuntime:
    """Never-ending autonomous engineering company loop."""

    def __init__(
        self,
        *,
        repo_orchestrator: MultiRepoOrchestrator | None = None,
        improvement_engine: ContinuousImprovementEngine | None = None,
        feature_engine: AutonomousFeatureGenerationEngine | None = None,
        git_agent: GitAgent | None = None,
        self_reviewer: SelfReviewEngine | None = None,
        pr_generator: AutonomousPRGenerator | None = None,
        executor_pool: ExecutorWorkerPool | None = None,
        event_bus: EventBus | None = None,
        task_source: TaskSource | None = None,
        config: CompanyRuntimeConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.repo_orchestrator = repo_orchestrator or MultiRepoOrchestrator()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=2, event_bus=self.event_bus)
        self.improvement_engine = improvement_engine or ContinuousImprovementEngine(
            repo_orchestrator=self.repo_orchestrator,
            event_bus=self.event_bus,
        )
        self.feature_engine = feature_engine or AutonomousFeatureGenerationEngine(
            repo_orchestrator=self.repo_orchestrator,
            event_bus=self.event_bus,
        )
        self.git_agent = git_agent or GitAgent(event_bus=self.event_bus)
        self.self_reviewer = self_reviewer or SelfReviewEngine(event_bus=self.event_bus)
        self.pr_generator = pr_generator or AutonomousPRGenerator(event_bus=self.event_bus)
        self.task_source = task_source
        self.config = config or CompanyRuntimeConfig()
        self._stop_requested = False
        self._cycle_counter = itertools.count(1)

    async def run_once(self, cycle_id: str | None = None) -> CompanyCycleResult:
        cycle = cycle_id or f"company-cycle-{next(self._cycle_counter):06d}"
        try:
            await self._publish(cycle, CompanyRuntimeStage.DETECTING, "Detecting tasks and improvements")
            tasks = await self.detect_tasks(cycle)
            if not tasks:
                await self._publish(cycle, CompanyRuntimeStage.IDLE, "No safe autonomous work detected")
                return CompanyCycleResult(cycle_id=cycle, success=True, stage=CompanyRuntimeStage.IDLE)

            results: list[CompanyTaskResult] = []
            for task in tasks[: self.config.max_tasks_per_cycle]:
                results.append(await self.execute_task(task))

            success = all(result.success for result in results)
            stage = CompanyRuntimeStage.COMPLETED if success else CompanyRuntimeStage.FAILED
            await self._publish(
                cycle,
                stage,
                "Company cycle completed" if success else "Company cycle completed with failures",
                {"task_results": [result.to_dict() for result in results]},
            )
            return CompanyCycleResult(
                cycle_id=cycle,
                success=success,
                stage=stage,
                detected_tasks=tasks,
                task_results=tuple(results),
            )
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            await self._publish(cycle, CompanyRuntimeStage.FAILED, error)
            return CompanyCycleResult(cycle_id=cycle, success=False, stage=CompanyRuntimeStage.FAILED, error=error)

    async def run_forever(self, *, max_cycles: int | None = None) -> tuple[CompanyCycleResult, ...]:
        results: list[CompanyCycleResult] = []
        self._stop_requested = False
        while not self._stop_requested:
            if max_cycles is not None and len(results) >= max_cycles:
                break
            results.append(await self.run_once())
            if self._stop_requested:
                break
            await asyncio.sleep(self.config.cycle_interval_seconds)
        return tuple(results)

    def stop(self) -> None:
        self._stop_requested = True

    def run_once_sync(self, cycle_id: str | None = None) -> CompanyCycleResult:
        return asyncio.run(self.run_once(cycle_id))

    async def detect_tasks(self, cycle_id: str) -> tuple[CompanyTask, ...]:
        tasks: list[CompanyTask] = []
        if self.task_source is not None:
            sourced = self.task_source()
            if isawaitable(sourced):
                sourced = await sourced
            tasks.extend(sourced)

        scans = await self.improvement_engine.scan_repositories(cycle_id)
        candidates = self.improvement_engine.detect_improvements(scans)
        tasks.extend(self._company_tasks_from_improvements(self.improvement_engine.generate_tasks(candidates)))
        tasks.sort(key=lambda task: (-task.priority, task.task_id))
        return tuple(tasks[: self.config.max_tasks_per_cycle])

    async def execute_task(self, task: CompanyTask) -> CompanyTaskResult:
        plan = self.repo_orchestrator.plan_task(task_id=task.task_id, goal=task.requirement, max_repos=1)
        assignments = self.assign_agents(task)
        await self._publish(
            task.task_id,
            CompanyRuntimeStage.ASSIGNING,
            "Assigned autonomous company agents",
            {"assignments": [assignment.to_dict() for assignment in assignments], "plan": plan.to_dict()},
        )

        feature_result = await self._execute_feature(task)
        if not feature_result.success:
            return CompanyTaskResult(task=task, success=False, plan=plan, assignments=assignments, feature_result=feature_result, error=feature_result.error)

        git_result = await self._execute_git(task)
        if not git_result.success:
            return CompanyTaskResult(
                task=task,
                success=False,
                plan=plan,
                assignments=assignments,
                feature_result=feature_result,
                git_result=git_result,
                error=git_result.error,
            )

        self_review_result = await self.self_reviewer.run(
            SelfReviewRequest(
                task_id=task.task_id,
                requirement=task.requirement,
                repo_path=self._repo(task).path,
                git_result=git_result,
                feature_result=feature_result,
            )
        )
        if not self_review_result.approved:
            return CompanyTaskResult(
                task=task,
                success=False,
                plan=plan,
                assignments=assignments,
                feature_result=feature_result,
                git_result=git_result,
                self_review_result=self_review_result,
                error="self-review rejected task",
            )

        pr_result = await self.pr_generator.run(
            PRGenerationRequest(
                task_id=task.task_id,
                goal=task.requirement,
                git_result=git_result,
                feature_result=feature_result,
                repo_path=self._repo(task).path,
                labels=("autonomous-company",),
            )
        )
        if not pr_result.success:
            return CompanyTaskResult(
                task=task,
                success=False,
                plan=plan,
                assignments=assignments,
                feature_result=feature_result,
                git_result=git_result,
                self_review_result=self_review_result,
                pr_result=pr_result,
                error=pr_result.error,
            )

        deploy_validation = await self.deploy_ready_validation(task)
        return CompanyTaskResult(
            task=task,
            success=deploy_validation.success,
            plan=plan,
            assignments=assignments,
            feature_result=feature_result,
            git_result=git_result,
            self_review_result=self_review_result,
            pr_result=pr_result,
            deploy_validation=deploy_validation,
            error=deploy_validation.error,
        )

    def assign_agents(self, task: CompanyTask) -> tuple[CompanyAssignment, ...]:
        return (
            CompanyAssignment(task.task_id, AgentType.PLANNER, "Create implementation plan", CompanyRuntimeStage.PLANNING),
            CompanyAssignment(task.task_id, AgentType.EXECUTOR, "Execute code changes and tests", CompanyRuntimeStage.EXECUTING),
            CompanyAssignment(task.task_id, AgentType.REVIEWER, "Review execution and self-review results", CompanyRuntimeStage.REVIEWING),
            CompanyAssignment(task.task_id, "git_agent", "Create branch, commit, and push", CompanyRuntimeStage.EXECUTING),
            CompanyAssignment(task.task_id, "pr_generator", "Generate production-ready pull request", CompanyRuntimeStage.PR_GENERATING),
            CompanyAssignment(task.task_id, "deploy_validator", "Run deploy-ready validation", CompanyRuntimeStage.DEPLOY_VALIDATING),
        )

    async def deploy_ready_validation(self, task: CompanyTask) -> DeployValidationResult:
        checks: list[dict[str, Any]] = []
        repo = self._repo(task)
        for index, command in enumerate(self.config.deploy_validation_commands, start=1):
            node = TaskGraphNode(
                id=f"{task.task_id}:deploy:{index:03d}",
                type=TaskGraphNodeType.EXECUTE,
                payload={
                    "task_id": task.task_id,
                    "tool": "run_command",
                    "input": {"cmd": command, "cwd": repo.path},
                    "lock_key": f"cwd:{repo.path}",
                },
            )
            result = await self.executor_pool.node_runner(node)
            checks.append(
                {
                    "command": command,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }
            )
        success = all(check["success"] for check in checks)
        return DeployValidationResult(
            success=success,
            checks=tuple(checks),
            error=None if success else "deploy-ready validation failed",
        )

    async def _execute_feature(self, task: CompanyTask) -> FeatureEngineResult:
        return await self.feature_engine.run(
            FeatureRequest(
                feature_id=task.task_id,
                description=task.requirement,
                test_commands=task.improvement_task.test_commands if task.improvement_task else (),
                max_repos=1,
                metadata={"company_task": task.to_dict()},
            )
        )

    async def _execute_git(self, task: CompanyTask) -> GitAutonomyResult:
        repo = self._repo(task)
        changed_paths = task.improvement_task.candidate.affected_paths if task.improvement_task else ()
        return await self.git_agent.run(
            GitAutonomyRequest(
                task_id=task.task_id,
                description=task.requirement,
                repo_path=repo.path,
                repo_id=repo.repo_id,
                changed_paths=changed_paths,
                push=True,
                metadata={"company_task": task.to_dict()},
            )
        )

    def _company_tasks_from_improvements(self, tasks: tuple[ImprovementTask, ...]) -> tuple[CompanyTask, ...]:
        return tuple(
            CompanyTask(
                task_id=task.task_id,
                requirement=task.requirement,
                repo=task.repo,
                improvement_task=task,
                priority=task.candidate.priority,
                metadata={"source": "continuous_improvement", "candidate": task.candidate.to_dict()},
            )
            for task in tasks
        )

    def _repo(self, task: CompanyTask) -> RepositoryMetadata:
        if task.repo is not None:
            return task.repo
        routes = self.repo_orchestrator.route_task(task_id=task.task_id, goal=task.requirement, max_repos=1)
        if routes:
            return self.repo_orchestrator.registry.get(routes[0].repo_id)
        repos = self.repo_orchestrator.registry.all()
        if not repos:
            raise ValueError("no repositories available for company task")
        return repos[0]

    async def _publish(
        self,
        task_id: str,
        stage: CompanyRuntimeStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = OrchestrationEvent(
            event_type=EventType.TASK_FAILED if stage == CompanyRuntimeStage.FAILED else EventType.TASK_STATE_CHANGED,
            task_id=task_id,
            message=message,
            payload={"stage": stage.value, **(payload or {})},
        )
        published = self.event_bus.publish(event)
        if isawaitable(published):
            await published


__all__ = [
    "AutonomousCompanyRuntime",
    "CompanyAssignment",
    "CompanyCycleResult",
    "CompanyRuntimeConfig",
    "CompanyRuntimeStage",
    "CompanyTask",
    "CompanyTaskResult",
    "DeployValidationResult",
    "TaskSource",
]
