import unittest

from anubis.distributed import (
    AttackGenerationRequest,
    AttackGenerator,
    AttackTarget,
    AttackType,
    ScenarioLibrary,
)


class AttackGeneratorTest(unittest.TestCase):
    def test_generates_required_attack_output_shape(self) -> None:
        scenarios = AttackGenerator().generate(AttackGenerationRequest(task_id="red-team-001", sandbox_id="sandbox-001"))

        self.assertGreaterEqual(len(scenarios), 8)
        for scenario in scenarios:
            payload = scenario.to_dict()
            self.assertEqual(set(payload), {"attack_id", "type", "target", "payload"})
            self.assertTrue(payload["attack_id"].startswith("attack_"))
            self.assertIn(payload["type"], {item.value for item in AttackType})
            self.assertIn(payload["target"], {item.value for item in AttackTarget})
            self.assertTrue(payload["payload"]["simulation_only"])
            self.assertEqual(payload["payload"]["task_id"], "red-team-001")

    def test_all_scenarios_are_sandbox_only_and_host_safe(self) -> None:
        scenarios = AttackGenerator().generate()

        for scenario in scenarios:
            sandbox = scenario.payload["sandbox"]
            self.assertTrue(sandbox["required"])
            self.assertFalse(sandbox["host_filesystem_access"])
            self.assertFalse(sandbox["host_mutation_allowed"])
            self.assertNotIn("execute_now", scenario.payload)

    def test_scenario_library_covers_requested_attack_classes(self) -> None:
        scenarios = ScenarioLibrary().scenarios()

        attack_types = {scenario.type for scenario in scenarios}
        names = {scenario.payload["name"] for scenario in scenarios}

        self.assertEqual(
            attack_types,
            {
                AttackType.TOOL_ABUSE,
                AttackType.FILESYSTEM,
                AttackType.EVENT_FLOODING,
                AttackType.LOGIC_CORRUPTION,
            },
        )
        self.assertIn("executor_attempts_planner_action", names)
        self.assertIn("executor_privilege_escalation", names)
        self.assertIn("path_traversal_attempt", names)
        self.assertIn("unauthorized_write_attempt", names)
        self.assertIn("massive_task_injection", names)
        self.assertIn("queue_overload_simulation", names)
        self.assertIn("invalid_dag_injection", names)
        self.assertIn("circular_dependency_graph", names)

    def test_filters_by_type_and_max_scenarios(self) -> None:
        request = AttackGenerationRequest(
            include_types=(AttackType.FILESYSTEM,),
            max_scenarios=1,
        )

        scenarios = AttackGenerator().generate(request)

        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0].type, AttackType.FILESYSTEM)

    def test_logic_corruption_payloads_model_invalid_dags_only(self) -> None:
        scenarios = AttackGenerator().generate(AttackGenerationRequest(include_types=(AttackType.LOGIC_CORRUPTION,)))
        by_name = {scenario.payload["name"]: scenario for scenario in scenarios}

        invalid = by_name["invalid_dag_injection"].payload
        circular = by_name["circular_dependency_graph"].payload

        self.assertEqual(invalid["nodes"][0]["depends_on"], ["missing-node"])
        self.assertEqual(circular["nodes"][0]["depends_on"], ["execute-b"])
        self.assertEqual(circular["nodes"][1]["depends_on"], ["plan-a"])
        self.assertEqual(invalid["expected_defense"], "dag_builder_unknown_dependency_rejection")
        self.assertEqual(circular["expected_defense"], "dag_cycle_detection")

    def test_generate_dicts_returns_serializable_scenarios(self) -> None:
        payloads = AttackGenerator().generate_dicts(AttackGenerationRequest(max_scenarios=2))

        self.assertEqual(len(payloads), 2)
        self.assertTrue(all(isinstance(payload["payload"], dict) for payload in payloads))


if __name__ == "__main__":
    unittest.main()
