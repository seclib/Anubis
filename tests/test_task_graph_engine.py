import asyncio
import time
import unittest

from anubis.distributed import (
    DAGBuilder,
    EventBus,
    EventType,
    ExecutionPlan,
    NodeExecutionResult,
    PlanStep,
    PlanStepType,
    TaskGraphError,
    TaskGraphScheduler,
)


def sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
        task_id="task-graph",
        steps=(
            PlanStep(
                id="step_a",
                action="Implement A",
                depends_on=(),
                type=PlanStepType.FILE,
            ),
            PlanStep(
                id="step_b",
                action="Implement B",
                depends_on=(),
                type=PlanStepType.FILE,
            ),
            PlanStep(
                id="step_c",
                action="Validate A and B",
                depends_on=("step_a", "step_b"),
                type=PlanStepType.SHELL,
            ),
        ),
    )


class TaskGraphEngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        if hasattr(self, "event_bus"):
            await self.event_bus.drain()
            self.event_bus.close()

    async def test_dag_builder_converts_planner_output_to_task_graph(self) -> None:
        graph = DAGBuilder().from_plan(sample_plan())

        self.assertEqual(graph.task_id, "task-graph")
        self.assertEqual(
            graph.to_dict(),
            {
                "task_id": "task-graph",
                "nodes": [
                    {"id": "plan", "type": "plan", "depends_on": [], "payload": {"task_id": "task-graph"}},
                    {
                        "id": "step_a",
                        "type": "execute",
                        "depends_on": ["plan"],
                        "payload": {"action": "Implement A", "step_type": "file"},
                    },
                    {
                        "id": "step_b",
                        "type": "execute",
                        "depends_on": ["plan"],
                        "payload": {"action": "Implement B", "step_type": "file"},
                    },
                    {
                        "id": "step_c",
                        "type": "execute",
                        "depends_on": ["step_a", "step_b"],
                        "payload": {"action": "Validate A and B", "step_type": "shell"},
                    },
                    {
                        "id": "verify",
                        "type": "verify",
                        "depends_on": ["step_c"],
                        "payload": {"task_id": "task-graph"},
                    },
                ],
            },
        )

    async def test_dag_builder_detects_parallelizable_nodes(self) -> None:
        builder = DAGBuilder()
        graph = builder.from_plan(sample_plan())

        groups = builder.topological_groups(graph)

        self.assertEqual([[node.id for node in group] for group in groups], [["plan"], ["step_a", "step_b"], ["step_c"], ["verify"]])

    async def test_dag_builder_rejects_cycles(self) -> None:
        plan = {
            "task_id": "cycle",
            "steps": [
                {"id": "a", "action": "A", "depends_on": ["b"], "type": "analysis"},
                {"id": "b", "action": "B", "depends_on": ["a"], "type": "analysis"},
            ],
        }

        with self.assertRaises(TaskGraphError):
            DAGBuilder().from_plan(plan)

    async def test_scheduler_runs_independent_nodes_in_parallel(self) -> None:
        graph = DAGBuilder().from_plan(sample_plan())
        started: list[str] = []

        async def runner(node):
            started.append(node.id)
            await asyncio.sleep(0.05 if node.id in {"step_a", "step_b"} else 0.001)
            return {"node_id": node.id, "success": True, "output": node.type.value}

        started_at = time.perf_counter()
        result = await TaskGraphScheduler().run(graph, runner)
        elapsed = time.perf_counter() - started_at

        self.assertTrue(result.success)
        self.assertLess(elapsed, 0.09)
        self.assertEqual(result.groups, (("plan",), ("step_a", "step_b"), ("step_c",), ("verify",)))
        self.assertEqual(started, ["plan", "step_a", "step_b", "step_c", "verify"])

    async def test_scheduler_waits_for_dependencies_and_blocks_dependents_on_failure(self) -> None:
        graph = DAGBuilder().from_plan(sample_plan())

        async def runner(node):
            if node.id == "step_a":
                return NodeExecutionResult(node_id=node.id, success=False, error="failed")
            return NodeExecutionResult(node_id=node.id, success=True, output=node.id)

        result = await TaskGraphScheduler().run(graph, runner)
        by_id = {item.node_id: item for item in result.results}

        self.assertFalse(result.success)
        self.assertFalse(by_id["step_a"].success)
        self.assertTrue(by_id["step_b"].success)
        self.assertFalse(by_id["step_c"].success)
        self.assertEqual(by_id["step_c"].error, "dependency failed")
        self.assertFalse(by_id["verify"].success)

    async def test_scheduler_emits_step_events(self) -> None:
        self.event_bus = EventBus()
        graph = DAGBuilder().from_plan(sample_plan())
        event_types: list[EventType] = []
        self.event_bus.subscribe(None, lambda event: event_types.append(event.event_type))

        async def runner(node):
            return NodeExecutionResult(node_id=node.id, success=True, output=node.id)

        await TaskGraphScheduler(event_bus=self.event_bus).run(graph, runner)
        await self.event_bus.drain()

        self.assertIn(EventType.STEP_STARTED, event_types)
        self.assertIn(EventType.STEP_COMPLETED, event_types)
        self.assertNotIn(EventType.STEP_FAILED, event_types)


if __name__ == "__main__":
    unittest.main()
