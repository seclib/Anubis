"""Autonomous execution engine for ANUBIS distributed software tasks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from anubis.distributed.dag_builder import DAGBuilder
from anubis.distributed.event_bus import EventBus
from anubis.distributed.planner_agent import PlannerAgent
from anubis.distributed.reviewer_agent import ReviewerAgent
from anubis.distributed.rollback import ReviewRecommendation
from anubis.distributed.scheduler import TaskGraphScheduler
from anubis.distributed.state_machine import DistributedStateMachine
from anubis.distributed.task_graph import (
    NodeExecutionResult,
    TaskGraph,
    TaskGraphNode,
    TaskGraphNodeType,
    TaskGraphRun,
)
from anubis.distributed.transition_validator import DistributedTaskState
from anubis.distributed.worker_pool import ExecutorWorkerPool


ExecutionNodeMapper = Callable[[TaskGraphNode], TaskGraphNode]


@dataclass(frozen=True)
class AutonomousEngineResult:
    task_id: str
    success: bool
    state: DistributedTaskState
    attempts: int
    graph: TaskGraph | None = None
    runs: tuple[TaskGraphRun, ...] = ()
    review: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "state": self.state.value,
            "attempts": self.attempts,
            "graph": self.graph.to_dict() if self.graph is not None else None,
            "runs": [run.to_dict() for run in self.runs],
            "review": dict(self.review) if self.review is not None else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class AutonomousEngineConfig:
    max_attempts: int = 3
    fail_fast: bool = False


class DefaultExecutionNodeMapper:
    """Maps graph execute nodes to safe concrete tool payloads.

    The mapper is intentionally conservative. Real deployments can inject a
    richer mapper that turns domain-specific plan nodes into write/command/git
    tool calls after policy approval.
    """

    def __call__(self, node: TaskGraphNode) -> TaskGraphNode:
        if node.type != TaskGraphNodeType.EXECUTE or node.payload.get("tool"):
            return node

        action = str(node.payload.get("action", node.id))
        step_type = str(node.payload.get("step_type", "analysis"))
        if step_type == "shell":
            payload = {
                **node.payload,
                "tool": "run_command",
                "input": {"cmd": "python -m compileall ."},
            }
        else:
            payload = {
                **node.payload,
                "tool": "search_codebase",
                "input": {"query": action},
            }
        return replace(node, payload=payload)


class AutonomousExecutionEngine:
    """End-to-end autonomous loop over planner, DAG, executor pool, reviewer, and state."""

    def __init__(
        self,
        *,
        planner: PlannerAgent | None = None,
        dag_builder: DAGBuilder | None = None,
        scheduler: TaskGraphScheduler | None = None,
        executor_pool: ExecutorWorkerPool | None = None,
        reviewer: ReviewerAgent | None = None,
        state_machine: DistributedStateMachine | None = None,
        event_bus: EventBus | None = None,
        node_mapper: ExecutionNodeMapper | None = None,
        config: AutonomousEngineConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.planner = planner or PlannerAgent()
        self.dag_builder = dag_builder or DAGBuilder()
        self.scheduler = scheduler or TaskGraphScheduler(event_bus=self.event_bus)
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=4, event_bus=self.event_bus)
        self.reviewer = reviewer or ReviewerAgent()
        self.state_machine = state_machine or DistributedStateMachine(event_bus=self.event_bus)
        self.node_mapper = node_mapper or DefaultExecutionNodeMapper()
        self.config = config or AutonomousEngineConfig()

    async def run(self, task_id: str, goal: str) -> AutonomousEngineResult:
        attempts = 0
        runs: list[TaskGraphRun] = []
        graph: TaskGraph | None = None
        last_review: dict[str, Any] | None = None
        last_error: str | None = None

        try:
            self.state_machine.create_task(task_id, metadata={"goal": goal})
            plan = self.planner.plan(task_id, goal)
            self.state_machine.transition(
                task_id,
                DistributedTaskState.PLANNED,
                reason="planner produced DAG input",
                metadata={"plan": plan.to_dict()},
            )
            graph = self._map_graph(self.dag_builder.from_plan(plan))

            while attempts < self.config.max_attempts:
                attempts += 1
                self._transition_for_attempt(task_id, attempts)
                run = await self.scheduler.run(graph, self._run_graph_node)
                runs.append(run)

                self.state_machine.transition(
                    task_id,
                    DistributedTaskState.VERIFYING,
                    reason="graph execution finished",
                    metadata={"attempt": attempts, "graph_run": run.to_dict()},
                )
                review = self._review_run(task_id, run)
                last_review = review.to_dict()

                if review.valid:
                    completed = self.state_machine.transition(
                        task_id,
                        DistributedTaskState.COMPLETED,
                        reason="review approved graph run",
                        metadata={"review": last_review},
                    )
                    return AutonomousEngineResult(
                        task_id=task_id,
                        success=True,
                        state=completed.state,
                        attempts=attempts,
                        graph=graph,
                        runs=tuple(runs),
                        review=last_review,
                    )

                if review.recommendation == ReviewRecommendation.ROLLBACK:
                    blocked = self.state_machine.transition(
                        task_id,
                        DistributedTaskState.BLOCKED,
                        reason="review requested rollback",
                        metadata={"review": last_review},
                    )
                    if self.config.fail_fast:
                        return AutonomousEngineResult(
                            task_id=task_id,
                            success=False,
                            state=blocked.state,
                            attempts=attempts,
                            graph=graph,
                            runs=tuple(runs),
                            review=last_review,
                            error="rollback requested",
                        )

                self.state_machine.transition(
                    task_id,
                    DistributedTaskState.RETRYING,
                    reason="review rejected graph run",
                    metadata={"attempt": attempts, "review": last_review},
                )

            failed = self.state_machine.transition(
                task_id,
                DistributedTaskState.FAILED,
                reason="maximum autonomous attempts exhausted",
                metadata={"attempts": attempts, "review": last_review or {}},
            )
            return AutonomousEngineResult(
                task_id=task_id,
                success=False,
                state=failed.state,
                attempts=attempts,
                graph=graph,
                runs=tuple(runs),
                review=last_review,
                error="maximum autonomous attempts exhausted",
            )
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            try:
                current = self.state_machine.get(task_id)
                if current.state not in {DistributedTaskState.COMPLETED, DistributedTaskState.FAILED}:
                    current = self.state_machine.transition(
                        task_id,
                        DistributedTaskState.FAILED,
                        reason=last_error,
                    )
                state = current.state
            except Exception:
                state = DistributedTaskState.FAILED
            return AutonomousEngineResult(
                task_id=task_id,
                success=False,
                state=state,
                attempts=attempts,
                graph=graph,
                runs=tuple(runs),
                review=last_review,
                error=last_error,
            )

    async def _run_graph_node(self, node: TaskGraphNode) -> NodeExecutionResult:
        if node.type in {TaskGraphNodeType.PLAN, TaskGraphNodeType.VERIFY}:
            return NodeExecutionResult(node_id=node.id, success=True, output=node.payload)
        return await self.executor_pool.node_runner(node)

    def _map_graph(self, graph: TaskGraph) -> TaskGraph:
        return TaskGraph(
            task_id=graph.task_id,
            nodes=tuple(self.node_mapper(node) for node in graph.nodes),
        )

    def _review_run(self, task_id: str, run: TaskGraphRun):
        failed = [result for result in run.results if not result.success]
        output = run.to_dict()
        return self.reviewer.review(
            {
                "step_id": task_id,
                "success": run.success,
                "output": output,
                "expected": {"contains": [task_id]},
                "state_checks": [
                    {
                        "name": "graph_run",
                        "expected": "success",
                        "actual": "success" if run.success else "failed",
                        "broken": False,
                    }
                ],
                "command_checks": [
                    {
                        "cmd": result.node_id,
                        "success": result.success,
                        "code": 0 if result.success else 1,
                    }
                    for result in failed
                ],
            }
        )

    def _transition_for_attempt(self, task_id: str, attempts: int) -> None:
        if attempts == 1:
            self.state_machine.transition(
                task_id,
                DistributedTaskState.EXECUTING,
                reason="starting graph execution",
                metadata={"attempt": attempts},
            )
            return
        self.state_machine.transition(
            task_id,
            DistributedTaskState.EXECUTING,
            reason="retrying graph execution",
            metadata={"attempt": attempts},
        )


__all__ = [
    "AutonomousEngineConfig",
    "AutonomousEngineResult",
    "AutonomousExecutionEngine",
    "DefaultExecutionNodeMapper",
    "ExecutionNodeMapper",
]
