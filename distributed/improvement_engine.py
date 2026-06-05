"""Continuous improvement engine for ANUBIS autonomous codebases."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.feature_engine import AutonomousFeatureGenerationEngine, FeatureEngineResult, FeatureRequest
from anubis.distributed.git_agent import GitAgent, GitAutonomyRequest, GitAutonomyResult
from anubis.distributed.multi_repo_orchestrator import MultiRepoOrchestrator, RepositoryMetadata
from anubis.distributed.pr_generator import AutonomousPRGenerator, PRGenerationRequest, PRGenerationResult
from anubis.distributed.self_reviewer import SelfReviewEngine, SelfReviewRequest, SelfReviewResult
from anubis.distributed.task_graph import NodeExecutionResult, TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class ImprovementKind(StrEnum):
    PERFORMANCE = "performance"
    MISSING_TESTS = "missing_tests"
    REFACTOR = "refactor"


class ImprovementRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImprovementStage(StrEnum):
    SCANNED = "scanned"
    DETECTED = "detected"
    TASKS_GENERATED = "tasks_generated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class RepositoryScan:
    repo_id: str
    repo: RepositoryMetadata
    success: bool
    output: str
    signals: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "repo": self.repo.to_dict(),
            "success": self.success,
            "output": self.output,
            "signals": list(self.signals),
            "error": self.error,
        }


@dataclass(frozen=True)
class ImprovementCandidate:
    candidate_id: str
    repo_id: str
    kind: ImprovementKind
    title: str
    description: str
    risk: ImprovementRisk
    priority: int
    evidence: tuple[str, ...] = ()
    affected_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "repo_id": self.repo_id,
            "kind": self.kind.value,
            "title": self.title,
            "description": self.description,
            "risk": self.risk.value,
            "priority": self.priority,
            "evidence": list(self.evidence),
            "affected_paths": list(self.affected_paths),
        }


@dataclass(frozen=True)
class ImprovementTask:
    task_id: str
    candidate: ImprovementCandidate
    repo: RepositoryMetadata
    requirement: str
    test_commands: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "candidate": self.candidate.to_dict(),
            "repo": self.repo.to_dict(),
            "requirement": self.requirement,
            "test_commands": list(self.test_commands),
        }


@dataclass(frozen=True)
class ImprovementExecutionResult:
    task: ImprovementTask
    success: bool
    feature_result: FeatureEngineResult | None = None
    git_result: GitAutonomyResult | None = None
    self_review_result: SelfReviewResult | None = None
    pr_result: PRGenerationResult | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "success": self.success,
            "feature_result": self.feature_result.to_dict() if self.feature_result else None,
            "git_result": self.git_result.to_dict() if self.git_result else None,
            "self_review_result": self.self_review_result.to_dict() if self.self_review_result else None,
            "pr_result": self.pr_result.to_dict() if self.pr_result else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class ImprovementCycleResult:
    cycle_id: str
    success: bool
    scans: tuple[RepositoryScan, ...]
    candidates: tuple[ImprovementCandidate, ...]
    tasks: tuple[ImprovementTask, ...]
    executions: tuple[ImprovementExecutionResult, ...]
    stage: ImprovementStage
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "success": self.success,
            "scans": [scan.to_dict() for scan in self.scans],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "tasks": [task.to_dict() for task in self.tasks],
            "executions": [execution.to_dict() for execution in self.executions],
            "stage": self.stage.value,
            "error": self.error,
        }


@dataclass(frozen=True)
class ImprovementEngineConfig:
    max_tasks_per_cycle: int = 3
    allow_high_risk: bool = False
    scan_query: str = "performance missing tests refactor duplicate slow TODO FIXME"
    default_test_command: str = "pytest"


ImprovementPipelineRunner = Callable[[ImprovementTask], ImprovementExecutionResult | Awaitable[ImprovementExecutionResult]]


class ContinuousImprovementEngine:
    """Scans repositories, creates safe improvement tasks, and executes them through the pipeline."""

    PERFORMANCE_TERMS = frozenset({"performance", "slow", "latency", "n+1", "quadratic", "o(n^2)", "inefficient"})
    MISSING_TEST_TERMS = frozenset({"missing tests", "untested", "no tests", "coverage gap", "test gap"})
    REFACTOR_TERMS = frozenset({"duplicate", "duplication", "refactor", "large function", "todo", "fixme", "complex"})

    def __init__(
        self,
        *,
        repo_orchestrator: MultiRepoOrchestrator | None = None,
        executor_pool: ExecutorWorkerPool | None = None,
        feature_engine: AutonomousFeatureGenerationEngine | None = None,
        git_agent: GitAgent | None = None,
        self_reviewer: SelfReviewEngine | None = None,
        pr_generator: AutonomousPRGenerator | None = None,
        event_bus: EventBus | None = None,
        pipeline_runner: ImprovementPipelineRunner | None = None,
        config: ImprovementEngineConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.repo_orchestrator = repo_orchestrator or MultiRepoOrchestrator()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=3, event_bus=self.event_bus)
        self.feature_engine = feature_engine or AutonomousFeatureGenerationEngine(
            repo_orchestrator=self.repo_orchestrator,
            event_bus=self.event_bus,
        )
        self.git_agent = git_agent or GitAgent(event_bus=self.event_bus)
        self.self_reviewer = self_reviewer or SelfReviewEngine(event_bus=self.event_bus)
        self.pr_generator = pr_generator or AutonomousPRGenerator(event_bus=self.event_bus)
        self.pipeline_runner = pipeline_runner
        self.config = config or ImprovementEngineConfig()

    async def run_cycle(self, cycle_id: str = "continuous-improvement") -> ImprovementCycleResult:
        try:
            scans = await self.scan_repositories(cycle_id)
            await self._publish(cycle_id, ImprovementStage.SCANNED, "Repository scan completed", {"scans": [scan.to_dict() for scan in scans]})
            candidates = self.detect_improvements(scans)
            await self._publish(
                cycle_id,
                ImprovementStage.DETECTED,
                "Improvement candidates detected",
                {"candidates": [candidate.to_dict() for candidate in candidates]},
            )
            tasks = self.generate_tasks(candidates)
            await self._publish(
                cycle_id,
                ImprovementStage.TASKS_GENERATED,
                "Safe improvement tasks generated",
                {"tasks": [task.to_dict() for task in tasks]},
            )
            executions = await self.execute_tasks(tasks)
            success = all(execution.success for execution in executions)
            stage = ImprovementStage.COMPLETED if success else ImprovementStage.FAILED
            await self._publish(
                cycle_id,
                stage,
                "Continuous improvement cycle completed" if success else "Continuous improvement cycle failed",
                {"executions": [execution.to_dict() for execution in executions]},
            )
            return ImprovementCycleResult(
                cycle_id=cycle_id,
                success=success,
                scans=scans,
                candidates=candidates,
                tasks=tasks,
                executions=executions,
                stage=stage,
            )
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            await self._publish(cycle_id, ImprovementStage.FAILED, error)
            return ImprovementCycleResult(
                cycle_id=cycle_id,
                success=False,
                scans=(),
                candidates=(),
                tasks=(),
                executions=(),
                stage=ImprovementStage.FAILED,
                error=error,
            )

    def run_cycle_sync(self, cycle_id: str = "continuous-improvement") -> ImprovementCycleResult:
        return asyncio.run(self.run_cycle(cycle_id))

    async def scan_repositories(self, cycle_id: str) -> tuple[RepositoryScan, ...]:
        scans = await asyncio.gather(*(self._scan_repo(cycle_id, repo) for repo in self.repo_orchestrator.registry.all()))
        return tuple(scans)

    async def _scan_repo(self, cycle_id: str, repo: RepositoryMetadata) -> RepositoryScan:
        node = TaskGraphNode(
            id=f"{cycle_id}:scan:{repo.repo_id}",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": cycle_id,
                "repo_id": repo.repo_id,
                "tool": "search_codebase",
                "input": {
                    "query": self.config.scan_query,
                    "cwd": repo.path,
                    "structure": list(repo.structure),
                    "language": repo.language,
                },
            },
        )
        result = await self.executor_pool.node_runner(node)
        output = _stringify(result.output)
        signals = self._signals(repo, output)
        return RepositoryScan(
            repo_id=repo.repo_id,
            repo=repo,
            success=result.success,
            output=output,
            signals=signals,
            error=result.error,
        )

    def detect_improvements(self, scans: tuple[RepositoryScan, ...]) -> tuple[ImprovementCandidate, ...]:
        candidates: list[ImprovementCandidate] = []
        for scan in scans:
            if not scan.success:
                continue
            candidates.extend(self._candidates_for_scan(scan))
        return tuple(sorted(candidates, key=lambda candidate: (_risk_order(candidate.risk), -candidate.priority, candidate.candidate_id)))

    def generate_tasks(self, candidates: tuple[ImprovementCandidate, ...]) -> tuple[ImprovementTask, ...]:
        tasks: list[ImprovementTask] = []
        repos = {repo.repo_id: repo for repo in self.repo_orchestrator.registry.all()}
        for candidate in candidates:
            if candidate.risk == ImprovementRisk.HIGH and not self.config.allow_high_risk:
                continue
            repo = repos[candidate.repo_id]
            tasks.append(
                ImprovementTask(
                    task_id=f"improve-{candidate.candidate_id}",
                    candidate=candidate,
                    repo=repo,
                    requirement=self._requirement(candidate),
                    test_commands=self._test_commands(repo),
                )
            )
            if len(tasks) >= self.config.max_tasks_per_cycle:
                break
        return tuple(tasks)

    async def execute_tasks(self, tasks: tuple[ImprovementTask, ...]) -> tuple[ImprovementExecutionResult, ...]:
        results: list[ImprovementExecutionResult] = []
        for task in tasks:
            await self._publish(task.task_id, ImprovementStage.EXECUTING, "Executing safe improvement task", {"task": task.to_dict()})
            if self.pipeline_runner is not None:
                result = self.pipeline_runner(task)
                if isawaitable(result):
                    result = await result
                results.append(result)
            else:
                results.append(await self._execute_full_pipeline(task))
        return tuple(results)

    async def _execute_full_pipeline(self, task: ImprovementTask) -> ImprovementExecutionResult:
        feature_result = await self.feature_engine.run(
            FeatureRequest(
                feature_id=task.task_id,
                description=task.requirement,
                test_commands=task.test_commands,
                max_repos=1,
                metadata={"improvement": task.candidate.to_dict()},
            )
        )
        if not feature_result.success:
            return ImprovementExecutionResult(task=task, success=False, feature_result=feature_result, error=feature_result.error)

        git_result = await self.git_agent.run(
            GitAutonomyRequest(
                task_id=task.task_id,
                description=task.requirement,
                repo_path=task.repo.path,
                repo_id=task.repo.repo_id,
                changed_paths=task.candidate.affected_paths,
                push=True,
                metadata={"improvement": task.candidate.to_dict()},
            )
        )
        if not git_result.success:
            return ImprovementExecutionResult(task=task, success=False, feature_result=feature_result, git_result=git_result, error=git_result.error)

        self_review_result = await self.self_reviewer.run(
            SelfReviewRequest(
                task_id=task.task_id,
                requirement=task.requirement,
                repo_path=task.repo.path,
                git_result=git_result,
                feature_result=feature_result,
            )
        )
        if not self_review_result.approved:
            return ImprovementExecutionResult(
                task=task,
                success=False,
                feature_result=feature_result,
                git_result=git_result,
                self_review_result=self_review_result,
                error="self-review rejected improvement",
            )

        pr_result = await self.pr_generator.run(
            PRGenerationRequest(
                task_id=task.task_id,
                goal=task.requirement,
                git_result=git_result,
                feature_result=feature_result,
                repo_path=task.repo.path,
                labels=("autonomous-improvement", task.candidate.kind.value),
            )
        )
        return ImprovementExecutionResult(
            task=task,
            success=pr_result.success,
            feature_result=feature_result,
            git_result=git_result,
            self_review_result=self_review_result,
            pr_result=pr_result,
            error=pr_result.error,
        )

    def _candidates_for_scan(self, scan: RepositoryScan) -> tuple[ImprovementCandidate, ...]:
        text = f"{scan.output} {' '.join(scan.signals)}".lower()
        candidates: list[ImprovementCandidate] = []
        if self._contains_any(text, self.MISSING_TEST_TERMS) or "tests" not in " ".join(scan.repo.structure).lower():
            candidates.append(
                self._candidate(
                    scan,
                    ImprovementKind.MISSING_TESTS,
                    "Add missing regression tests",
                    "Add focused tests for currently under-covered behavior without changing production code.",
                    ImprovementRisk.LOW,
                    90,
                )
            )
        if self._contains_any(text, self.PERFORMANCE_TERMS):
            risk = ImprovementRisk.HIGH if any(term in text for term in ("database", "migration", "critical path")) else ImprovementRisk.MEDIUM
            candidates.append(
                self._candidate(
                    scan,
                    ImprovementKind.PERFORMANCE,
                    "Improve performance hotspot",
                    "Investigate and optimize a detected performance hotspot while preserving behavior.",
                    risk,
                    70,
                )
            )
        if self._contains_any(text, self.REFACTOR_TERMS):
            candidates.append(
                self._candidate(
                    scan,
                    ImprovementKind.REFACTOR,
                    "Refactor maintainability issue",
                    "Reduce duplication or local complexity with behavior-preserving refactoring.",
                    ImprovementRisk.MEDIUM,
                    60,
                )
            )
        return tuple(candidates)

    def _candidate(
        self,
        scan: RepositoryScan,
        kind: ImprovementKind,
        title: str,
        description: str,
        risk: ImprovementRisk,
        priority: int,
    ) -> ImprovementCandidate:
        candidate_id = f"{scan.repo_id}-{kind.value}"
        return ImprovementCandidate(
            candidate_id=candidate_id,
            repo_id=scan.repo_id,
            kind=kind,
            title=title,
            description=description,
            risk=risk,
            priority=priority,
            evidence=tuple(scan.signals or (scan.output[:240],)),
            affected_paths=self._affected_paths(scan),
        )

    def _signals(self, repo: RepositoryMetadata, output: str) -> tuple[str, ...]:
        signals = list(repo.tags) + list(repo.structure)
        lowered = output.lower()
        for term_group in (self.PERFORMANCE_TERMS, self.MISSING_TEST_TERMS, self.REFACTOR_TERMS):
            for term in sorted(term_group):
                if term in lowered:
                    signals.append(term)
        return tuple(dict.fromkeys(signal for signal in signals if signal))

    def _affected_paths(self, scan: RepositoryScan) -> tuple[str, ...]:
        paths = re.findall(r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|md)", scan.output)
        return tuple(dict.fromkeys(paths[:12]))

    def _requirement(self, candidate: ImprovementCandidate) -> str:
        return (
            f"{candidate.title} in repository {candidate.repo_id}. "
            f"{candidate.description} Safety constraint: preserve production behavior and keep validation passing."
        )

    def _test_commands(self, repo: RepositoryMetadata) -> tuple[str, ...]:
        commands = repo.metadata.get("test_commands")
        if isinstance(commands, (list, tuple)):
            return tuple(str(command) for command in commands)
        command = repo.metadata.get("test_command")
        if isinstance(command, str) and command.strip():
            return (command.strip(),)
        return (self.config.default_test_command,)

    def _contains_any(self, text: str, terms: frozenset[str]) -> bool:
        return any(term in text for term in terms)

    async def _publish(
        self,
        task_id: str,
        stage: ImprovementStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = OrchestrationEvent(
            event_type=EventType.TASK_FAILED if stage == ImprovementStage.FAILED else EventType.TASK_STATE_CHANGED,
            task_id=task_id,
            message=message,
            payload={"stage": stage.value, **(payload or {})},
        )
        published = self.event_bus.publish(event)
        if isawaitable(published):
            await published


def _risk_order(risk: ImprovementRisk) -> int:
    return {ImprovementRisk.LOW: 0, ImprovementRisk.MEDIUM: 1, ImprovementRisk.HIGH: 2}[risk]


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


__all__ = [
    "ContinuousImprovementEngine",
    "ImprovementCandidate",
    "ImprovementCycleResult",
    "ImprovementEngineConfig",
    "ImprovementExecutionResult",
    "ImprovementKind",
    "ImprovementPipelineRunner",
    "ImprovementRisk",
    "ImprovementStage",
    "ImprovementTask",
    "RepositoryScan",
]
