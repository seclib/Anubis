"""Autonomous feature generation engine for ANUBIS Level 3."""

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
from anubis.distributed.multi_repo_orchestrator import CrossRepoPlan, MultiRepoOrchestrator, RepoTaskRoute
from anubis.distributed.planner_agent import PlannerAgent
from anubis.distributed.planning_schema import ExecutionPlan, PlanStep, PlanStepType
from anubis.distributed.reviewer_agent import ReviewerAgent
from anubis.distributed.rollback import ReviewRecommendation
from anubis.distributed.scheduler import TaskGraphScheduler
from anubis.distributed.task_graph import NodeExecutionResult, TaskGraph, TaskGraphNode, TaskGraphNodeType, TaskGraphRun
from anubis.distributed.worker_pool import ExecutorWorkerPool


FeatureStepMapperResult = TaskGraphNode | tuple[TaskGraphNode, ...] | None
FeatureStepMapper = Callable[
    ["FeatureRequest", RepoTaskRoute, PlanStep, "FeatureAttemptContext"],
    FeatureStepMapperResult,
]
AsyncNodeRunner = Callable[[TaskGraphNode], NodeExecutionResult | Awaitable[NodeExecutionResult]]


class FeatureStage(StrEnum):
    RECEIVED = "received"
    ANALYZED = "analyzed"
    PLANNED = "planned"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    FIXING = "fixing"
    PREPARING_PR = "preparing_pr"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class FeatureFileChange:
    path: str
    content: str
    repo_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "path": self.path,
            "content": self.content,
        }


@dataclass(frozen=True)
class FeatureRequest:
    feature_id: str
    description: str
    file_changes: tuple[FeatureFileChange, ...] = ()
    test_commands: tuple[str, ...] = ()
    max_repos: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "description": self.description,
            "file_changes": [change.to_dict() for change in self.file_changes],
            "test_commands": list(self.test_commands),
            "max_repos": self.max_repos,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FeatureAttemptContext:
    attempt: int
    analysis: dict[str, Any]
    previous_failure: dict[str, Any] | None = None


@dataclass(frozen=True)
class PullRequestDraft:
    title: str
    body: str
    branch: str
    commits: tuple[dict[str, Any], ...] = ()
    diffs: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "branch": self.branch,
            "commits": [dict(commit) for commit in self.commits],
            "diffs": [dict(diff) for diff in self.diffs],
        }


@dataclass(frozen=True)
class FeatureRouteResult:
    repo_id: str
    route_id: str
    success: bool
    attempts: int
    analysis: dict[str, Any]
    plan: ExecutionPlan | None = None
    runs: tuple[TaskGraphRun, ...] = ()
    review: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "route_id": self.route_id,
            "success": self.success,
            "attempts": self.attempts,
            "analysis": dict(self.analysis),
            "plan": self.plan.to_dict() if self.plan else None,
            "runs": [run.to_dict() for run in self.runs],
            "review": dict(self.review) if self.review else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class FeatureEngineResult:
    feature_id: str
    success: bool
    stage: FeatureStage
    cross_repo_plan: CrossRepoPlan | None = None
    route_results: tuple[FeatureRouteResult, ...] = ()
    pr_draft: PullRequestDraft | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "success": self.success,
            "stage": self.stage.value,
            "cross_repo_plan": self.cross_repo_plan.to_dict() if self.cross_repo_plan else None,
            "route_results": [result.to_dict() for result in self.route_results],
            "pr_draft": self.pr_draft.to_dict() if self.pr_draft else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class FeatureEngineConfig:
    max_attempts: int = 3
    default_test_command: str = "pytest"
    prepare_commit: bool = True
    branch_prefix: str = "anubis/feature"


class DefaultFeatureStepMapper:
    """Maps planner file steps to deterministic write/search execution nodes."""

    def __call__(
        self,
        request: FeatureRequest,
        route: RepoTaskRoute,
        step: PlanStep,
        context: FeatureAttemptContext,
    ) -> FeatureStepMapperResult:
        if step.type == PlanStepType.ANALYSIS:
            return None
        if step.type == PlanStepType.SHELL:
            return None

        changes = tuple(
            change
            for change in request.file_changes
            if change.repo_id in {None, route.repo_id}
        )
        if changes:
            return tuple(
                TaskGraphNode(
                    id=f"{route.repo_id}:write:{step.id}:{index:03d}:{_safe_id(change.path)}",
                    type=TaskGraphNodeType.EXECUTE,
                    payload={
                        "task_id": request.feature_id,
                        "route_id": route.route_id,
                        "repo_id": route.repo_id,
                        "tool": "write_file",
                        "input": {"path": change.path, "content": change.content},
                    },
                )
                for index, change in enumerate(changes, start=1)
            )

        return TaskGraphNode(
            id=f"{route.repo_id}:inspect:{step.id}",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": request.feature_id,
                "route_id": route.route_id,
                "repo_id": route.repo_id,
                "tool": "search_codebase",
                "input": {
                    "query": f"{step.action} {context.previous_failure or ''}".strip(),
                    "cwd": context.analysis.get("repo_path"),
                },
            },
        )


class AutonomousFeatureGenerationEngine:
    """Coordinates feature implementation from request through PR-ready output."""

    def __init__(
        self,
        *,
        repo_orchestrator: MultiRepoOrchestrator | None = None,
        planner: PlannerAgent | None = None,
        scheduler: TaskGraphScheduler | None = None,
        executor_pool: ExecutorWorkerPool | None = None,
        reviewer: ReviewerAgent | None = None,
        event_bus: EventBus | None = None,
        step_mapper: FeatureStepMapper | None = None,
        config: FeatureEngineConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.repo_orchestrator = repo_orchestrator or MultiRepoOrchestrator()
        self.planner = planner or PlannerAgent()
        self.scheduler = scheduler or TaskGraphScheduler(event_bus=self.event_bus)
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=4, event_bus=self.event_bus)
        self.reviewer = reviewer or ReviewerAgent()
        self.step_mapper = step_mapper or DefaultFeatureStepMapper()
        self.config = config or FeatureEngineConfig()

    async def run(self, request: FeatureRequest | str, description: str | None = None) -> FeatureEngineResult:
        feature_request = self._request_from_input(request, description)
        cross_repo_plan: CrossRepoPlan | None = None
        route_results: tuple[FeatureRouteResult, ...] = ()

        try:
            await self._publish(EventType.TASK_CREATED, feature_request.feature_id, FeatureStage.RECEIVED, "Feature request received")
            cross_repo_plan = self.repo_orchestrator.plan_task(
                task_id=feature_request.feature_id,
                goal=feature_request.description,
                max_repos=feature_request.max_repos,
            )
            if not cross_repo_plan.routes:
                return await self._fail(feature_request, cross_repo_plan, (), "no active repositories available")

            route_results = await self._run_routes(feature_request, cross_repo_plan)
            if not all(result.success for result in route_results):
                await self._publish(
                    EventType.TASK_FAILED,
                    feature_request.feature_id,
                    FeatureStage.FAILED,
                    "One or more repository routes failed",
                    payload={"route_results": [result.to_dict() for result in route_results]},
                )
                return FeatureEngineResult(
                    feature_id=feature_request.feature_id,
                    success=False,
                    stage=FeatureStage.FAILED,
                    cross_repo_plan=cross_repo_plan,
                    route_results=route_results,
                    error="one or more repository routes failed",
                )

            await self._publish(
                EventType.TASK_STATE_CHANGED,
                feature_request.feature_id,
                FeatureStage.PREPARING_PR,
                "Preparing pull request draft",
                payload={"route_results": [result.to_dict() for result in route_results]},
            )
            pr_draft = self._prepare_pr_draft(feature_request, route_results)
            await self._publish(
                EventType.TASK_COMPLETED,
                feature_request.feature_id,
                FeatureStage.COMPLETED,
                "Feature implementation completed and PR draft prepared",
                payload={"pr_draft": pr_draft.to_dict()},
            )
            return FeatureEngineResult(
                feature_id=feature_request.feature_id,
                success=True,
                stage=FeatureStage.COMPLETED,
                cross_repo_plan=cross_repo_plan,
                route_results=route_results,
                pr_draft=pr_draft,
            )
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            await self._publish(EventType.TASK_FAILED, feature_request.feature_id, FeatureStage.FAILED, error)
            return FeatureEngineResult(
                feature_id=feature_request.feature_id,
                success=False,
                stage=FeatureStage.FAILED,
                cross_repo_plan=cross_repo_plan,
                route_results=route_results,
                error=error,
            )

    def run_sync(self, request: FeatureRequest | str, description: str | None = None) -> FeatureEngineResult:
        return asyncio.run(self.run(request, description))

    async def _run_routes(
        self,
        request: FeatureRequest,
        cross_repo_plan: CrossRepoPlan,
    ) -> tuple[FeatureRouteResult, ...]:
        completed: dict[str, FeatureRouteResult] = {}
        results: list[FeatureRouteResult] = []

        for group in self._route_groups(cross_repo_plan.routes):
            blocked = [
                route
                for route in group
                if any(not completed[dependency].success for dependency in route.depends_on if dependency in completed)
            ]
            for route in blocked:
                result = FeatureRouteResult(
                    repo_id=route.repo_id,
                    route_id=route.route_id,
                    success=False,
                    attempts=0,
                    analysis={},
                    error="repository route dependency failed",
                )
                completed[route.route_id] = result
                results.append(result)

            runnable = tuple(route for route in group if route not in blocked)
            if not runnable:
                continue
            group_results = await asyncio.gather(*(self._run_route(request, route) for route in runnable))
            for result in group_results:
                completed[result.route_id] = result
                results.append(result)

        return tuple(results)

    def _route_groups(self, routes: tuple[RepoTaskRoute, ...]) -> tuple[tuple[RepoTaskRoute, ...], ...]:
        remaining = {route.route_id: route for route in routes}
        completed: set[str] = set()
        groups: list[tuple[RepoTaskRoute, ...]] = []

        while remaining:
            ready = tuple(
                remaining[route_id]
                for route_id in sorted(remaining)
                if all(dependency not in remaining or dependency in completed for dependency in remaining[route_id].depends_on)
            )
            if not ready:
                ready = (remaining[sorted(remaining)[0]],)
            groups.append(ready)
            for route in ready:
                completed.add(route.route_id)
                remaining.pop(route.route_id, None)

        return tuple(groups)

    async def _run_route(self, request: FeatureRequest, route: RepoTaskRoute) -> FeatureRouteResult:
        analysis = await self._analyze_route(request, route)
        await self._publish(
            EventType.TASK_STATE_CHANGED,
            request.feature_id,
            FeatureStage.ANALYZED,
            f"Repository analyzed: {route.repo_id}",
            subtask_id=route.route_id,
            payload={"analysis": analysis},
        )

        plan = self.planner.plan(route.route_id, self._planning_prompt(request, route, analysis))
        await self._publish(
            EventType.TASK_STATE_CHANGED,
            request.feature_id,
            FeatureStage.PLANNED,
            f"Repository implementation planned: {route.repo_id}",
            subtask_id=route.route_id,
            payload={"plan": plan.to_dict()},
        )

        runs: list[TaskGraphRun] = []
        previous_failure: dict[str, Any] | None = None
        last_review: dict[str, Any] | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            stage = FeatureStage.IMPLEMENTING if attempt == 1 else FeatureStage.FIXING
            await self._publish(
                EventType.TASK_STATE_CHANGED,
                request.feature_id,
                stage,
                f"Repository route attempt {attempt}: {route.repo_id}",
                subtask_id=route.route_id,
                payload={"attempt": attempt, "previous_failure": previous_failure or {}},
            )
            graph = self._build_route_graph(
                request,
                route,
                plan,
                FeatureAttemptContext(
                    attempt=attempt,
                    analysis=analysis,
                    previous_failure=previous_failure,
                ),
            )
            await self._publish(
                EventType.TASK_STATE_CHANGED,
                request.feature_id,
                FeatureStage.TESTING,
                f"Repository route validation graph started: {route.repo_id}",
                subtask_id=route.route_id,
                payload={"attempt": attempt, "graph": graph.to_dict()},
            )
            run = await self.scheduler.run(graph, self._run_node)
            runs.append(run)
            review = self._review_route_run(route, run)
            last_review = review.to_dict()
            if review.valid:
                return FeatureRouteResult(
                    repo_id=route.repo_id,
                    route_id=route.route_id,
                    success=True,
                    attempts=attempt,
                    analysis=analysis,
                    plan=plan,
                    runs=tuple(runs),
                    review=last_review,
                )
            if review.recommendation == ReviewRecommendation.ROLLBACK:
                return FeatureRouteResult(
                    repo_id=route.repo_id,
                    route_id=route.route_id,
                    success=False,
                    attempts=attempt,
                    analysis=analysis,
                    plan=plan,
                    runs=tuple(runs),
                    review=last_review,
                    error="review requested rollback",
                )
            previous_failure = {
                "attempt": attempt,
                "review": last_review,
                "failed_nodes": [result.to_dict() for result in run.results if not result.success],
            }

        return FeatureRouteResult(
            repo_id=route.repo_id,
            route_id=route.route_id,
            success=False,
            attempts=self.config.max_attempts,
            analysis=analysis,
            plan=plan,
            runs=tuple(runs),
            review=last_review,
            error="maximum feature self-fix attempts exhausted",
        )

    async def _analyze_route(self, request: FeatureRequest, route: RepoTaskRoute) -> dict[str, Any]:
        repo = self.repo_orchestrator.registry.get(route.repo_id)
        node = TaskGraphNode(
            id=f"{route.repo_id}:analysis",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": request.feature_id,
                "route_id": route.route_id,
                "repo_id": route.repo_id,
                "tool": "search_codebase",
                "input": {
                    "query": request.description,
                    "cwd": repo.path,
                    "structure": list(repo.structure),
                    "language": repo.language,
                },
            },
        )
        result = await self.executor_pool.node_runner(node)
        return {
            "repo_id": route.repo_id,
            "repo_path": repo.path,
            "language": repo.language,
            "structure": list(repo.structure),
            "success": result.success,
            "output": result.output,
            "error": result.error,
        }

    def _build_route_graph(
        self,
        request: FeatureRequest,
        route: RepoTaskRoute,
        plan: ExecutionPlan,
        context: FeatureAttemptContext,
    ) -> TaskGraph:
        nodes: list[TaskGraphNode] = [
            TaskGraphNode(
                id=f"{route.repo_id}:plan",
                type=TaskGraphNodeType.PLAN,
                payload={"plan": plan.to_dict(), "attempt": context.attempt},
            )
        ]

        implementation_ids: list[str] = []
        for step in plan.steps:
            mapped = self.step_mapper(request, route, step, context)
            for node in self._normalize_nodes(mapped):
                depends_on = tuple(node.depends_on or (f"{route.repo_id}:plan",))
                normalized = TaskGraphNode(
                    id=node.id,
                    type=node.type,
                    depends_on=depends_on,
                    payload={**node.payload, "task_id": request.feature_id, "route_id": route.route_id, "attempt": context.attempt},
                )
                nodes.append(normalized)
                if normalized.type == TaskGraphNodeType.EXECUTE:
                    implementation_ids.append(normalized.id)

        test_ids = self._append_test_nodes(request, route, nodes, implementation_ids)
        diff_id = self._append_diff_node(request, route, nodes, test_ids or implementation_ids)
        self._append_commit_node(request, route, nodes, (diff_id,))
        return TaskGraph(task_id=route.route_id, nodes=tuple(nodes))

    def _append_test_nodes(
        self,
        request: FeatureRequest,
        route: RepoTaskRoute,
        nodes: list[TaskGraphNode],
        implementation_ids: list[str],
    ) -> tuple[str, ...]:
        repo = self.repo_orchestrator.registry.get(route.repo_id)
        commands = request.test_commands or tuple(repo.metadata.get("test_commands", ()) or ())
        if not commands:
            commands = (str(repo.metadata.get("test_command", self.config.default_test_command)),)

        test_ids: list[str] = []
        depends_on = tuple(implementation_ids or (f"{route.repo_id}:plan",))
        for index, command in enumerate(commands, start=1):
            node_id = f"{route.repo_id}:test:{index:03d}"
            test_ids.append(node_id)
            nodes.append(
                TaskGraphNode(
                    id=node_id,
                    type=TaskGraphNodeType.EXECUTE,
                    depends_on=depends_on,
                    payload={
                        "tool": "run_command",
                        "input": {"cmd": command, "cwd": repo.path},
                        "lock_key": f"cwd:{repo.path}",
                    },
                )
            )
        return tuple(test_ids)

    def _append_diff_node(
        self,
        request: FeatureRequest,
        route: RepoTaskRoute,
        nodes: list[TaskGraphNode],
        depends_on: tuple[str, ...],
    ) -> str:
        repo = self.repo_orchestrator.registry.get(route.repo_id)
        node_id = f"{route.repo_id}:diff"
        nodes.append(
            TaskGraphNode(
                id=node_id,
                type=TaskGraphNodeType.EXECUTE,
                depends_on=tuple(depends_on or (f"{route.repo_id}:plan",)),
                payload={
                    "tool": "git_diff",
                    "input": {"cwd": repo.path},
                    "lock_key": f"git:{repo.path}",
                },
            )
        )
        return node_id

    def _append_commit_node(
        self,
        request: FeatureRequest,
        route: RepoTaskRoute,
        nodes: list[TaskGraphNode],
        depends_on: tuple[str, ...],
    ) -> None:
        if not self.config.prepare_commit:
            return
        repo = self.repo_orchestrator.registry.get(route.repo_id)
        nodes.append(
            TaskGraphNode(
                id=f"{route.repo_id}:commit",
                type=TaskGraphNodeType.EXECUTE,
                depends_on=depends_on,
                payload={
                    "tool": "git_commit",
                    "input": {
                        "cwd": repo.path,
                        "message": f"Implement {request.feature_id}: {request.description}",
                    },
                    "lock_key": f"git:{repo.path}",
                },
            )
        )

    async def _run_node(self, node: TaskGraphNode) -> NodeExecutionResult:
        if node.type in {TaskGraphNodeType.PLAN, TaskGraphNodeType.VERIFY}:
            return NodeExecutionResult(node_id=node.id, success=True, output=node.payload)
        return await self.executor_pool.node_runner(node)

    def _review_route_run(self, route: RepoTaskRoute, run: TaskGraphRun):
        failed = [result for result in run.results if not result.success]
        return self.reviewer.review(
            {
                "step_id": route.route_id,
                "success": run.success,
                "output": run.to_dict(),
                "expected": {"contains": [route.repo_id]},
                "command_checks": [
                    {
                        "cmd": result.node_id,
                        "success": result.success,
                        "code": 0 if result.success else 1,
                    }
                    for result in failed
                ],
                "state_checks": [
                    {
                        "name": "feature_route",
                        "expected": "success",
                        "actual": "success" if run.success else "failed",
                        "broken": False,
                    }
                ],
            }
        )

    def _prepare_pr_draft(
        self,
        request: FeatureRequest,
        route_results: tuple[FeatureRouteResult, ...],
    ) -> PullRequestDraft:
        commits: list[dict[str, Any]] = []
        diffs: list[dict[str, Any]] = []
        for route_result in route_results:
            for run in route_result.runs:
                for result in run.results:
                    if result.node_id.endswith(":commit"):
                        commits.append({"repo_id": route_result.repo_id, "output": result.output, "success": result.success})
                    if result.node_id.endswith(":diff"):
                        diffs.append({"repo_id": route_result.repo_id, "output": result.output, "success": result.success})

        return PullRequestDraft(
            title=f"Implement {request.feature_id}",
            body=self._pr_body(request, route_results),
            branch=f"{self.config.branch_prefix}/{_safe_id(request.feature_id)}",
            commits=tuple(commits),
            diffs=tuple(diffs),
        )

    def _pr_body(self, request: FeatureRequest, route_results: tuple[FeatureRouteResult, ...]) -> str:
        repos = ", ".join(result.repo_id for result in route_results)
        attempts = sum(result.attempts for result in route_results)
        return (
            f"Feature request: {request.description}\n\n"
            f"Repositories: {repos}\n"
            f"Autonomous attempts: {attempts}\n"
            "Validation: implementation graph completed successfully."
        )

    async def _fail(
        self,
        request: FeatureRequest,
        cross_repo_plan: CrossRepoPlan | None,
        route_results: tuple[FeatureRouteResult, ...],
        error: str,
    ) -> FeatureEngineResult:
        await self._publish(EventType.TASK_FAILED, request.feature_id, FeatureStage.FAILED, error)
        return FeatureEngineResult(
            feature_id=request.feature_id,
            success=False,
            stage=FeatureStage.FAILED,
            cross_repo_plan=cross_repo_plan,
            route_results=route_results,
            error=error,
        )

    async def _publish(
        self,
        event_type: EventType,
        task_id: str,
        stage: FeatureStage,
        message: str,
        *,
        subtask_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = OrchestrationEvent(
            event_type=event_type,
            task_id=task_id,
            subtask_id=subtask_id,
            message=message,
            payload={"stage": stage.value, **(payload or {})},
        )
        published = self.event_bus.publish(event)
        if isawaitable(published):
            await published

    def _request_from_input(self, request: FeatureRequest | str, description: str | None) -> FeatureRequest:
        if isinstance(request, FeatureRequest):
            if not request.feature_id.strip():
                raise ValueError("feature_id is required")
            if not request.description.strip():
                raise ValueError("feature description is required")
            return request
        feature_id = request.strip()
        if not feature_id:
            raise ValueError("feature_id is required")
        if description is None or not description.strip():
            raise ValueError("feature description is required")
        return FeatureRequest(feature_id=feature_id, description=description.strip())

    def _planning_prompt(self, request: FeatureRequest, route: RepoTaskRoute, analysis: dict[str, Any]) -> str:
        return (
            f"{route.goal}. "
            f"Use analysis from repo {route.repo_id}: {analysis.get('output', '')}. "
            "Implement code changes, run tests, and prepare PR evidence."
        )

    def _normalize_nodes(self, mapped: FeatureStepMapperResult) -> tuple[TaskGraphNode, ...]:
        if mapped is None:
            return ()
        if isinstance(mapped, TaskGraphNode):
            return (mapped,)
        return tuple(mapped)


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return normalized or "feature"


__all__ = [
    "AutonomousFeatureGenerationEngine",
    "DefaultFeatureStepMapper",
    "FeatureAttemptContext",
    "FeatureEngineConfig",
    "FeatureEngineResult",
    "FeatureFileChange",
    "FeatureRequest",
    "FeatureRouteResult",
    "FeatureStage",
    "FeatureStepMapper",
    "PullRequestDraft",
]
