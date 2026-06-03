import unittest

from anubis.distributed import (
    DependencyResolutionError,
    DependencyResolver,
    ExecutionPlan,
    PlannerAgent,
    PlanStep,
    PlanStepType,
)


class PhaseB2PlannerAgentTest(unittest.TestCase):
    def test_planner_outputs_required_structured_plan_shape(self) -> None:
        plan = PlannerAgent().plan_dict(
            "task-123",
            "implement executor agent and update reviewer agent",
        )

        self.assertEqual(set(plan), {"task_id", "steps"})
        self.assertEqual(plan["task_id"], "task-123")
        self.assertGreaterEqual(len(plan["steps"]), 4)
        for step in plan["steps"]:
            self.assertEqual(set(step), {"id", "action", "depends_on", "type"})
            self.assertIsInstance(step["depends_on"], list)
            self.assertIn(step["type"], {"file", "shell", "analysis"})

    def test_planner_exposes_parallel_implementation_opportunities(self) -> None:
        agent = PlannerAgent()
        plan = agent.plan("task-456", "implement executor agent and update reviewer agent")

        groups = agent.dependency_resolver.parallel_groups(plan)

        self.assertEqual([step.id for step in groups[0]], ["step_001"])
        self.assertGreaterEqual(len(groups[1]), 2)
        self.assertTrue(all(step.depends_on == ("step_001",) for step in groups[1]))

    def test_dependency_resolver_rejects_unknown_dependencies(self) -> None:
        plan = ExecutionPlan(
            task_id="task-bad",
            steps=(
                PlanStep(
                    id="step_001",
                    action="Analyze task",
                    depends_on=("missing",),
                    type=PlanStepType.ANALYSIS,
                ),
            ),
        )

        with self.assertRaises(DependencyResolutionError):
            DependencyResolver().validate(plan)

    def test_dependency_resolver_rejects_cycles(self) -> None:
        plan = ExecutionPlan(
            task_id="task-cycle",
            steps=(
                PlanStep(
                    id="step_001",
                    action="First",
                    depends_on=("step_002",),
                    type=PlanStepType.ANALYSIS,
                ),
                PlanStep(
                    id="step_002",
                    action="Second",
                    depends_on=("step_001",),
                    type=PlanStepType.FILE,
                ),
            ),
        )

        with self.assertRaises(DependencyResolutionError):
            DependencyResolver().validate(plan)

    def test_planner_is_deterministic(self) -> None:
        agent = PlannerAgent()
        first = agent.plan_dict("task-stable", "fix routing and validate tests")
        second = agent.plan_dict("task-stable", "fix routing and validate tests")

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
