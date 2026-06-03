import unittest
from dataclasses import replace

from anubis.distributed import (
    AutonomousEngineConfig,
    AutonomousExecutionEngine,
    DistributedStateMachine,
    DistributedTaskState,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    InMemoryStatePersistence,
    ReviewRecommendation,
    ReviewResult,
    TaskGraphNode,
    TaskGraphNodeType,
)


class RecordingExecutor:
    calls: list[str] = []
    fail_first: bool = False
    failed_once: bool = False

    def execute(self, step):
        type(self).calls.append(step["step_id"])
        if type(self).fail_first and not type(self).failed_once and step["step_id"].startswith("step_"):
            type(self).failed_once = True
            return ExecutionResult(
                step_id=step["step_id"],
                success=False,
                output="temporary executor failure",
                logs=("failed once",),
            )
        return ExecutionResult(
            step_id=step["step_id"],
            success=True,
            output=f"executed:{step['step_id']}",
            logs=("ok",),
        )


class RollbackReviewer:
    def review(self, payload):
        return ReviewResult(
            step_id=str(payload.get("step_id", "")),
            valid=False,
            issues=("rollback required",),
            recommendation=ReviewRecommendation.ROLLBACK,
        )


def tool_mapper(node: TaskGraphNode) -> TaskGraphNode:
    if node.type != TaskGraphNodeType.EXECUTE:
        return node
    return replace(
        node,
        payload={
            **node.payload,
            "tool": "search_codebase",
            "input": {"query": node.id},
        },
    )


class AutonomousExecutionEngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RecordingExecutor.calls = []
        RecordingExecutor.fail_first = False
        RecordingExecutor.failed_once = False

    async def asyncTearDown(self) -> None:
        if hasattr(self, "event_bus"):
            await self.event_bus.drain()
            self.event_bus.close()

    def build_engine(
        self,
        *,
        max_attempts: int = 3,
        reviewer=None,
        fail_fast: bool = False,
    ) -> AutonomousExecutionEngine:
        self.event_bus = EventBus()
        persistence = InMemoryStatePersistence()
        state_machine = DistributedStateMachine(persistence=persistence, event_bus=self.event_bus)
        executor_pool = ExecutorWorkerPool(
            max_workers=3,
            executor_factory=RecordingExecutor,
            event_bus=self.event_bus,
        )
        return AutonomousExecutionEngine(
            event_bus=self.event_bus,
            state_machine=state_machine,
            executor_pool=executor_pool,
            reviewer=reviewer,
            node_mapper=tool_mapper,
            config=AutonomousEngineConfig(max_attempts=max_attempts, fail_fast=fail_fast),
        )

    async def test_autonomous_engine_runs_goal_to_completion(self) -> None:
        engine = self.build_engine()

        result = await engine.run("task-auto-1", "implement worker pool and validate tests")

        self.assertTrue(result.success)
        self.assertEqual(result.state, DistributedTaskState.COMPLETED)
        self.assertEqual(result.attempts, 1)
        self.assertIsNotNone(result.graph)
        self.assertTrue(RecordingExecutor.calls)
        self.assertEqual(engine.state_machine.get("task-auto-1").state, DistributedTaskState.COMPLETED)

    async def test_autonomous_engine_retries_after_failed_execution(self) -> None:
        RecordingExecutor.fail_first = True
        engine = self.build_engine(max_attempts=3)

        result = await engine.run("task-auto-2", "implement retryable task")

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        states = [entry["to"] for entry in engine.state_machine.get("task-auto-2").history]
        self.assertIn("retrying", states)
        self.assertEqual(states[-1], "completed")

    async def test_autonomous_engine_fails_after_max_attempts(self) -> None:
        class AlwaysFailExecutor:
            def execute(self, step):
                return ExecutionResult(
                    step_id=step["step_id"],
                    success=False,
                    output="permanent failure",
                    logs=("failed",),
                )

        self.event_bus = EventBus()
        state_machine = DistributedStateMachine(event_bus=self.event_bus)
        engine = AutonomousExecutionEngine(
            event_bus=self.event_bus,
            state_machine=state_machine,
            executor_pool=ExecutorWorkerPool(max_workers=2, executor_factory=AlwaysFailExecutor, event_bus=self.event_bus),
            node_mapper=tool_mapper,
            config=AutonomousEngineConfig(max_attempts=2),
        )

        result = await engine.run("task-auto-3", "implement impossible task")

        self.assertFalse(result.success)
        self.assertEqual(result.state, DistributedTaskState.FAILED)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.error, "maximum autonomous attempts exhausted")

    async def test_autonomous_engine_blocks_on_rollback_when_fail_fast(self) -> None:
        engine = self.build_engine(reviewer=RollbackReviewer(), fail_fast=True)

        result = await engine.run("task-auto-4", "implement risky task")

        self.assertFalse(result.success)
        self.assertEqual(result.state, DistributedTaskState.BLOCKED)
        self.assertEqual(result.error, "rollback requested")

    async def test_autonomous_engine_emits_state_and_step_events(self) -> None:
        engine = self.build_engine()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await engine.run("task-auto-5", "implement observable task")
        await self.event_bus.drain()

        self.assertTrue(result.success)
        event_types = [event.event_type for event in events]
        self.assertIn(EventType.TASK_STATE_CHANGED, event_types)
        self.assertIn(EventType.STEP_STARTED, event_types)
        self.assertIn(EventType.STEP_COMPLETED, event_types)


if __name__ == "__main__":
    unittest.main()
