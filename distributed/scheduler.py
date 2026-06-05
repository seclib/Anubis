"""Async DAG scheduler for ANUBIS task graphs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.dag_builder import DAGBuilder
from anubis.distributed.event_bus import EventBus
from anubis.distributed.task_graph import NodeExecutionResult, TaskGraph, TaskGraphNode, TaskGraphRun


NodeRunnerResult = NodeExecutionResult | dict[str, Any] | Any
NodeRunner = Callable[[TaskGraphNode], NodeRunnerResult | Awaitable[NodeRunnerResult]]


class TaskGraphScheduler:
    """Runs independent DAG nodes concurrently through an injected node runner."""

    def __init__(
        self,
        *,
        dag_builder: DAGBuilder | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.dag_builder = dag_builder or DAGBuilder()
        self.event_bus = event_bus

    async def run(self, graph: TaskGraph, runner: NodeRunner) -> TaskGraphRun:
        self.dag_builder.validate(graph)
        groups = self.dag_builder.topological_groups(graph)
        results: list[NodeExecutionResult] = []
        completed: set[str] = set()
        failed: set[str] = set()
        executed_groups: list[tuple[str, ...]] = []

        for group in groups:
            runnable = tuple(
                node
                for node in group
                if all(dependency in completed for dependency in node.depends_on)
            )
            blocked = tuple(node for node in group if node not in runnable)
            for node in blocked:
                results.append(
                    NodeExecutionResult(
                        node_id=node.id,
                        success=False,
                        error="dependency failed",
                    )
                )
                failed.add(node.id)

            if not runnable:
                continue

            executed_groups.append(tuple(node.id for node in runnable))
            group_results = await asyncio.gather(
                *(self._run_node(graph.task_id, node, runner) for node in runnable),
                return_exceptions=False,
            )
            results.extend(group_results)

            for result in group_results:
                if result.success:
                    completed.add(result.node_id)
                else:
                    failed.add(result.node_id)

        success = bool(results) and not failed and len(completed) == len(graph.nodes)
        return TaskGraphRun(
            task_id=graph.task_id,
            success=success,
            results=tuple(results),
            groups=tuple(executed_groups),
        )

    def run_sync(self, graph: TaskGraph, runner: NodeRunner) -> TaskGraphRun:
        return asyncio.run(self.run(graph, runner))

    async def _run_node(
        self,
        task_id: str,
        node: TaskGraphNode,
        runner: NodeRunner,
    ) -> NodeExecutionResult:
        await self._publish(EventType.STEP_STARTED, task_id, node, "Graph node started")
        try:
            raw_result = runner(node)
            if isawaitable(raw_result):
                raw_result = await raw_result
            result = self._normalize_result(node.id, raw_result)
        except Exception as exc:
            result = NodeExecutionResult(
                node_id=node.id,
                success=False,
                error=f"{exc.__class__.__name__}: {exc}",
            )

        await self._publish(
            EventType.STEP_COMPLETED if result.success else EventType.STEP_FAILED,
            task_id,
            node,
            "Graph node completed" if result.success else "Graph node failed",
            payload=result.to_dict(),
        )
        return result

    def _normalize_result(self, node_id: str, raw_result: NodeRunnerResult) -> NodeExecutionResult:
        if isinstance(raw_result, NodeExecutionResult):
            return raw_result
        if isinstance(raw_result, dict):
            success = bool(raw_result.get("success", True))
            return NodeExecutionResult(
                node_id=str(raw_result.get("node_id", node_id)),
                success=success,
                output=raw_result.get("output"),
                error=raw_result.get("error") if not success else None,
            )
        return NodeExecutionResult(node_id=node_id, success=True, output=raw_result)

    async def _publish(
        self,
        event_type: EventType,
        task_id: str,
        node: TaskGraphNode,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(
            OrchestrationEvent(
                event_type=event_type,
                task_id=task_id,
                subtask_id=node.id,
                message=message,
                payload={
                    "node_id": node.id,
                    "node_type": node.type.value,
                    **(payload or {}),
                },
            )
        )


__all__ = ["NodeRunner", "TaskGraphScheduler"]
