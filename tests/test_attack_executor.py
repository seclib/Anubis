import tempfile
import unittest

from anubis.distributed import (
    AttackExecutionLogger,
    AttackExecutionStatus,
    AttackExecutor,
    AttackGenerationRequest,
    AttackGenerator,
    AttackScenario,
    AttackTarget,
    AttackType,
    SandboxAttackRunner,
    SandboxRuntime,
    SandboxRuntimeConfig,
)


def scenarios_by_name():
    scenarios = AttackGenerator().generate(AttackGenerationRequest(task_id="red-team-001"))
    return {scenario.payload["name"]: scenario for scenario in scenarios}


class AttackExecutorTest(unittest.TestCase):
    def runner(self):
        root = tempfile.TemporaryDirectory()
        runtime = SandboxRuntime(SandboxRuntimeConfig(root_dir=root.name))
        logger = AttackExecutionLogger()
        return root, SandboxAttackRunner(runtime=runtime, logger=logger), logger

    def test_permission_bypass_attempt_is_simulated_and_contained(self) -> None:
        root, runner, _logger = self.runner()
        self.addCleanup(root.cleanup)
        scenario = scenarios_by_name()["executor_privilege_escalation"]

        result = runner.run(scenario)

        self.assertTrue(result.success)
        self.assertEqual(result.status, AttackExecutionStatus.CONTAINED)
        self.assertFalse(result.bypass_detected)
        self.assertFalse(result.system_response["real_tools_executed"])
        self.assertGreaterEqual(len(result.system_response["denied_permissions"]), 1)
        self.assertEqual(result.logs[-1].attack_id, scenario.attack_id)

    def test_filesystem_escape_is_blocked_without_host_access(self) -> None:
        root, runner, _logger = self.runner()
        self.addCleanup(root.cleanup)
        scenario = scenarios_by_name()["unauthorized_write_attempt"]

        result = runner.run(scenario)

        self.assertTrue(result.success)
        self.assertTrue(result.system_response["contained"])
        self.assertFalse(result.system_response["host_write_performed"])
        self.assertFalse(result.system_response["host_read_performed"])
        self.assertIn("absolute host paths are not allowed", result.system_response["reason"])

    def test_event_flooding_simulates_queue_overload_without_enqueuing_events(self) -> None:
        root, runner, _logger = self.runner()
        self.addCleanup(root.cleanup)
        scenario = scenarios_by_name()["massive_task_injection"]

        result = runner.run(scenario)

        self.assertTrue(result.success)
        self.assertEqual(result.system_response["execution_type"], "task_injection")
        self.assertEqual(result.system_response["real_events_enqueued"], 0)
        self.assertTrue(result.system_response["queue_overload_simulated"])
        self.assertTrue(result.system_response["backpressure_expected"])

    def test_logic_corruption_rejects_invalid_dag_and_cycle(self) -> None:
        root, runner, _logger = self.runner()
        self.addCleanup(root.cleanup)
        scenarios = scenarios_by_name()

        invalid = runner.run(scenarios["invalid_dag_injection"])
        circular = runner.run(scenarios["circular_dependency_graph"])

        self.assertTrue(invalid.success)
        self.assertTrue(circular.success)
        self.assertFalse(invalid.system_response["dag_valid"])
        self.assertFalse(circular.system_response["dag_valid"])
        self.assertIn("unknown", invalid.system_response["reason"])
        self.assertIn("cycle", circular.system_response["reason"])

    def test_invalid_non_simulation_attack_is_rejected_and_logged(self) -> None:
        root, runner, logger = self.runner()
        self.addCleanup(root.cleanup)
        scenario = AttackScenario(
            attack_id="attack_unsafe",
            type=AttackType.FILESYSTEM,
            target=AttackTarget.EXECUTOR,
            payload={
                "simulation_only": False,
                "sandbox": {"required": False, "host_filesystem_access": True, "host_mutation_allowed": True},
            },
        )

        result = runner.run(scenario)

        self.assertFalse(result.success)
        self.assertEqual(result.status, AttackExecutionStatus.INVALID)
        self.assertIn("simulation_only", result.error)
        self.assertFalse(logger.entries()[-1].success)

    def test_executor_runs_batches_and_reports_no_external_impact(self) -> None:
        root, runner, _logger = self.runner()
        self.addCleanup(root.cleanup)
        executor = AttackExecutor(runner)
        scenarios = AttackGenerator().generate(AttackGenerationRequest(max_scenarios=4))

        results = executor.execute_many(scenarios)

        self.assertEqual(len(results), 4)
        self.assertTrue(all(result.success for result in results))
        self.assertTrue(all(result.system_response.get("network_calls_made") is False for result in results))


if __name__ == "__main__":
    unittest.main()
