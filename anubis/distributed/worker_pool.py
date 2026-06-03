"""Async executor worker pool for ANUBIS task graph nodes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.executor_agent import ExecutionResult, ExecutorAgent
from anubis.distributed.task_graph import NodeExecutionResult, TaskGraphNode, TaskGraphNodeType


ExecutorFactory = Callable[[], ExecutorAgent]


@dataclass(frozen=True)
class ExecutorJob:
    job_id: str
    node: TaskGraphNode


@dataclass(frozen=True)
class ExecutorPoolResult:
    node_id: str
    worker_id: str
    success: bool
    output: str
    logs: tuple[str, ...] = ()
    error: str | None = None

    def to_node_result(self) -> NodeExecutionResult:
        return NodeExecutionResult(
            node_id=self.node_id,
            success=self.success,
            output=self.output,
            error=self.error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "worker_id": self.worker_id,
            "success": self.success,
            "output": self.output,
            "logs": list(self.logs),
            "error": self.error,
        }


class ResourceLockManager:
    """Provides deterministic async locks for shared execution resources."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def lock_for(self, key: str) -> asyncio.Lock:
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock


class ExecutorWorkerPool:
    """Queue-based async pool of ExecutorAgent workers."""

    def __init__(
        self,
        *,
        max_workers: int,
        executor_factory: ExecutorFactory | None = None,
        event_bus: EventBus | None = None,
        resource_locks: ResourceLockManager | None = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.max_workers = max_workers
        self.executor_factory = executor_factory or ExecutorAgent
        self.event_bus = event_bus
        self.resource_locks = resource_locks or ResourceLockManager()
        self.queue: asyncio.Queue[ExecutorJob] = asyncio.Queue()
        self._results: dict[str, ExecutorPoolResult] = {}
        self._results_lock = asyncio.Lock()
        self._job_counter = 0

    async def submit(self, node: TaskGraphNode) -> ExecutorJob:
        if node.type != TaskGraphNodeType.EXECUTE:
            raise ValueError(f"executor pool accepts execute nodes only: {node.id}")
        self._job_counter += 1
        job = ExecutorJob(job_id=f"job_{self._job_counter:06d}", node=node)
        await self.queue.put(job)
        return job

    async def execute_nodes(self, nodes: Iterable[TaskGraphNode]) -> tuple[ExecutorPoolResult, ...]:
        ordered_nodes = tuple(nodes)
        self._validate_unique_nodes(ordered_nodes)
        for node in ordered_nodes:
            await self.submit(node)

        workers = [
            asyncio.create_task(self._worker_loop(worker_id=f"executor-{index + 1:03d}"))
            for index in range(min(self.max_workers, max(1, len(ordered_nodes))))
        ]
        await self.queue.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        async with self._results_lock:
            return tuple(self._results[node.id] for node in ordered_nodes)

    async def node_runner(self, node: TaskGraphNode) -> NodeExecutionResult:
        results = await self.execute_nodes((node,))
        return results[0].to_node_result()

    async def _worker_loop(self, *, worker_id: str) -> None:
        executor = self.executor_factory()
        while True:
            job = await self.queue.get()
            try:
                result = await self._execute_job(job, worker_id=worker_id, executor=executor)
                async with self._results_lock:
                    self._results[job.node.id] = result
            finally:
                self.queue.task_done()

    async def _execute_job(
        self,
        job: ExecutorJob,
        *,
        worker_id: str,
        executor: ExecutorAgent,
    ) -> ExecutorPoolResult:
        await self._publish(EventType.STEP_STARTED, job, worker_id, "Executor worker started node")
        lock_key = self._resource_key(job.node)
        if lock_key is None:
            result = await self._run_executor(job.node, executor)
        else:
            lock = await self.resource_locks.lock_for(lock_key)
            async with lock:
                result = await self._run_executor(job.node, executor)

        pool_result = ExecutorPoolResult(
            node_id=job.node.id,
            worker_id=worker_id,
            success=result.success,
            output=result.output,
            logs=result.logs,
            error=None if result.success else result.output,
        )
        await self._publish(
            EventType.STEP_COMPLETED if pool_result.success else EventType.STEP_FAILED,
            job,
            worker_id,
            "Executor worker completed node" if pool_result.success else "Executor worker failed node",
            payload=pool_result.to_dict(),
        )
        return pool_result

    async def _run_executor(self, node: TaskGraphNode, executor: ExecutorAgent) -> ExecutionResult:
        step = self._execution_step_payload(node)
        return await asyncio.to_thread(executor.execute, step)

    def _execution_step_payload(self, node: TaskGraphNode) -> dict[str, Any]:
        tool = node.payload.get("tool")
        tool_input = node.payload.get("input", node.payload.get("tool_input", {}))
        if not isinstance(tool, str) or not tool.strip():
            return {
                "step_id": node.id,
                "tool": "",
                "input": {},
            }
        if not isinstance(tool_input, Mapping):
            tool_input = {}
        return {
            "step_id": node.id,
            "tool": tool,
            "input": dict(tool_input),
        }

    def _resource_key(self, node: TaskGraphNode) -> str | None:
        explicit = node.payload.get("lock_key")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

        tool = node.payload.get("tool")
        tool_input = node.payload.get("input", node.payload.get("tool_input", {}))
        if not isinstance(tool_input, Mapping):
            tool_input = {}

        if tool in {"git_diff", "git_commit"}:
            return "git"
        if tool == "write_file":
            path = tool_input.get("path")
            return f"file:{path}" if isinstance(path, str) and path else "file"
        if tool == "run_command":
            cwd = tool_input.get("cwd", ".")
            return f"cwd:{cwd}"
        return None

    def _validate_unique_nodes(self, nodes: tuple[TaskGraphNode, ...]) -> None:
        ids = [node.id for node in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("executor pool nodes must have unique ids")

    async def _publish(
        self,
        event_type: EventType,
        job: ExecutorJob,
        worker_id: str,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(
            OrchestrationEvent(
                event_type=event_type,
                task_id=str(job.node.payload.get("task_id", "")),
                subtask_id=job.node.id,
                agent_id=worker_id,
                message=message,
                payload={
                    "job_id": job.job_id,
                    "node_id": job.node.id,
                    "worker_id": worker_id,
                    **(payload or {}),
                },
            )
        )


__all__ = [
    "ExecutorFactory",
    "ExecutorJob",
    "ExecutorPoolResult",
    "ExecutorWorkerPool",
    "ResourceLockManager",
]
