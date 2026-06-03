import unittest

from anubis.distributed import (
    AgentRegistration,
    AgentResult,
    AgentType,
    DistributedOrchestrator,
    EventType,
    TaskStatus,
)


class PhaseB1OrchestratorTest(unittest.TestCase):
    def build_orchestrator(self, max_retries: int = 2) -> DistributedOrchestrator:
        orchestrator = DistributedOrchestrator(max_retries=max_retries)
        orchestrator.register_agent(
            AgentRegistration(agent_id="planner-1", agent_type=AgentType.PLANNER)
        )
        orchestrator.register_agent(
            AgentRegistration(agent_id="executor-1", agent_type=AgentType.EXECUTOR)
        )
        orchestrator.register_agent(
            AgentRegistration(agent_id="reviewer-1", agent_type=AgentType.REVIEWER)
        )
        return orchestrator

    def test_orchestrator_routes_workflow_without_executing_tools(self) -> None:
        orchestrator = self.build_orchestrator()

        receipt = orchestrator.receive_task("implement distributed orchestration")

        self.assertEqual(receipt.task.status, TaskStatus.ASSIGNED)
        self.assertEqual(len(receipt.assignments), 1)
        planner_assignment = receipt.assignments[0]
        self.assertEqual(planner_assignment.agent_type, AgentType.PLANNER)
        self.assertNotIn("tool", planner_assignment.context)

        receipt = orchestrator.complete_assignment(
            AgentResult(
                assignment_id=planner_assignment.assignment_id,
                success=True,
                output={"plan": ["dispatch executor", "review result"]},
            )
        )
        executor_assignment = receipt.assignments[0]
        self.assertEqual(executor_assignment.agent_type, AgentType.EXECUTOR)
        self.assertIn(planner_assignment.subtask_id, executor_assignment.context["dependency_results"])

        receipt = orchestrator.complete_assignment(
            AgentResult(
                assignment_id=executor_assignment.assignment_id,
                success=True,
                output={"execution": "completed by worker"},
            )
        )
        reviewer_assignment = receipt.assignments[0]
        self.assertEqual(reviewer_assignment.agent_type, AgentType.REVIEWER)

        receipt = orchestrator.complete_assignment(
            AgentResult(
                assignment_id=reviewer_assignment.assignment_id,
                success=True,
                output={"approved": True},
            )
        )

        self.assertEqual(receipt.task.status, TaskStatus.COMPLETED)
        self.assertEqual(receipt.assignments, ())
        self.assertEqual(len(receipt.task.result["subtasks"]), 3)

    def test_event_bus_records_required_events(self) -> None:
        orchestrator = self.build_orchestrator()
        receipt = orchestrator.receive_task("validate event flow")
        assignment = receipt.assignments[0]

        orchestrator.complete_assignment(
            AgentResult(assignment_id=assignment.assignment_id, success=True, output={})
        )

        event_types = [event.event_type for event in orchestrator.event_bus.events()]
        self.assertIn(EventType.TASK_CREATED, event_types)
        self.assertIn(EventType.TASK_ASSIGNED, event_types)
        self.assertIn(EventType.TASK_COMPLETED, event_types)

    def test_registry_supports_capacity_based_worker_scaling(self) -> None:
        orchestrator = DistributedOrchestrator()
        orchestrator.register_agent(
            AgentRegistration(agent_id="planner-pool", agent_type=AgentType.PLANNER, max_concurrent=2)
        )
        orchestrator.register_agent(
            AgentRegistration(agent_id="executor-1", agent_type=AgentType.EXECUTOR)
        )
        orchestrator.register_agent(
            AgentRegistration(agent_id="reviewer-1", agent_type=AgentType.REVIEWER)
        )

        first = orchestrator.receive_task("task one")
        second = orchestrator.receive_task("task two")

        self.assertEqual(first.assignments[0].agent_id, "planner-pool")
        self.assertEqual(second.assignments[0].agent_id, "planner-pool")
        planner = orchestrator.registry.list_agents(AgentType.PLANNER)[0]
        self.assertEqual(planner.active_assignments, 2)

    def test_failed_assignment_retries_before_terminal_failure(self) -> None:
        orchestrator = self.build_orchestrator(max_retries=1)
        receipt = orchestrator.receive_task("retry planner")
        first_assignment = receipt.assignments[0]

        retry = orchestrator.complete_assignment(
            AgentResult(
                assignment_id=first_assignment.assignment_id,
                success=False,
                error="temporary planner failure",
            )
        )
        self.assertEqual(len(retry.assignments), 1)
        self.assertEqual(retry.assignments[0].agent_type, AgentType.PLANNER)

        failed = orchestrator.complete_assignment(
            AgentResult(
                assignment_id=retry.assignments[0].assignment_id,
                success=False,
                error="permanent planner failure",
            )
        )

        self.assertEqual(failed.task.status, TaskStatus.FAILED)
        self.assertEqual(failed.assignments, ())
        self.assertTrue(
            any(
                event.event_type == EventType.TASK_FAILED
                and event.payload.get("retrying") is False
                for event in orchestrator.event_bus.events()
            )
        )


if __name__ == "__main__":
    unittest.main()
