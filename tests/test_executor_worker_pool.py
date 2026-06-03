import asyncio
import time
import unittest

from anubis.distributed import (
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    TaskGraphNode,
    TaskGraphNodeType,
)


class SleepExecutor:
    active = 0
    max_active = 0
    calls: list[str] = []
    lock = __import__("threading").Lock()

    def execute(self, step):
        with self.lock:
            type(self).active += 1
            type(self).max_active = max(type(self).max_active, type(self).active)
            type(self).calls.append(step["step_id"])
        try:
            time.sleep(float(step["input"].get("sleep", 0.02)))
            return ExecutionResult(
                step_id=step["step_id"],
                success=True,
                output=f"done:{step['step_id']}",
                logs=(f"ran:{step['tool']}",),
            )
        finally:
            with self.lock:
                type(self).active -= 1


class ExecutorWorkerPoolTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        SleepExecutor.active = 0
        SleepExecutor.max_active = 0
        SleepExecutor.calls = []

    async def asyncTearDown(self) -> None:
        if hasattr(self, "event_bus"):
            await self.event_bus.drain()
            self.event_bus.close()

    def node(
        self,
        node_id: str,
        *,
        tool: str = "search_codebase",
        lock_key: str | None = None,
        sleep: float = 0.02,
    ) -> TaskGraphNode:
        payload = {
            "task_id": "pool-task",
            "tool": tool,
            "input": {"query": "ok", "sleep": sleep},
        }
        if lock_key:
            payload["lock_key"] = lock_key
        return TaskGraphNode(id=node_id, type=TaskGraphNodeType.EXECUTE, payload=payload)

    async def test_worker_pool_executes_queue_with_multiple_executor_instances(self) -> None:
        pool = ExecutorWorkerPool(max_workers=3, executor_factory=SleepExecutor)
        nodes = tuple(self.node(f"node_{index}") for index in range(6))

        started = time.perf_counter()
        results = await pool.execute_nodes(nodes)
        elapsed = time.perf_counter() - started

        self.assertEqual([result.node_id for result in results], [node.id for node in nodes])
        self.assertTrue(all(result.success for result in results))
        self.assertEqual(SleepExecutor.max_active, 3)
        self.assertLess(elapsed, 0.08)

    async def test_worker_pool_limits_concurrency(self) -> None:
        pool = ExecutorWorkerPool(max_workers=2, executor_factory=SleepExecutor)
        nodes = tuple(self.node(f"node_{index}", sleep=0.03) for index in range(5))

        await pool.execute_nodes(nodes)

        self.assertLessEqual(SleepExecutor.max_active, 2)

    async def test_worker_pool_locks_shared_resources(self) -> None:
        pool = ExecutorWorkerPool(max_workers=3, executor_factory=SleepExecutor)
        nodes = tuple(
            self.node(f"node_{index}", tool="run_command", lock_key="shared", sleep=0.02)
            for index in range(3)
        )

        started = time.perf_counter()
        await pool.execute_nodes(nodes)
        elapsed = time.perf_counter() - started

        self.assertEqual(SleepExecutor.max_active, 1)
        self.assertGreaterEqual(elapsed, 0.055)

    async def test_worker_pool_rejects_non_execute_nodes(self) -> None:
        pool = ExecutorWorkerPool(max_workers=1, executor_factory=SleepExecutor)

        with self.assertRaises(ValueError):
            await pool.submit(TaskGraphNode(id="plan", type=TaskGraphNodeType.PLAN))

    async def test_worker_pool_emits_step_events(self) -> None:
        self.event_bus = EventBus()
        events: list[EventType] = []
        self.event_bus.subscribe(None, lambda event: events.append(event.event_type))
        pool = ExecutorWorkerPool(
            max_workers=2,
            executor_factory=SleepExecutor,
            event_bus=self.event_bus,
        )

        await pool.execute_nodes((self.node("node_a"), self.node("node_b")))
        await self.event_bus.drain()

        self.assertIn(EventType.STEP_STARTED, events)
        self.assertIn(EventType.STEP_COMPLETED, events)
        self.assertNotIn(EventType.STEP_FAILED, events)

    async def test_node_runner_integrates_with_scheduler_interface(self) -> None:
        pool = ExecutorWorkerPool(max_workers=1, executor_factory=SleepExecutor)

        result = await pool.node_runner(self.node("node_runner"))

        self.assertTrue(result.success)
        self.assertEqual(result.node_id, "node_runner")


if __name__ == "__main__":
    unittest.main()
