import unittest

from cli.agents import AgentRegistry


class AgentRegistryTest(unittest.TestCase):
    def test_initializes_core_agents(self) -> None:
        registry = AgentRegistry()

        self.assertEqual(
            registry.snapshot(),
            {
                "builder": "idle",
                "researcher": "idle",
                "analyst": "idle",
                "orchestrator": "active",
            },
        )

    def test_spawn_adds_extendable_agent(self) -> None:
        registry = AgentRegistry()

        result = registry.spawn("Reviewer")

        self.assertEqual(result, "reviewer spawned")
        self.assertEqual(registry.snapshot()["reviewer"], "idle")

    def test_update_changes_agent_state(self) -> None:
        registry = AgentRegistry()

        registry.update("builder", "running")
        registry.update("researcher", "completed")

        snapshot = registry.snapshot()
        self.assertEqual(snapshot["builder"], "running")
        self.assertEqual(snapshot["researcher"], "completed")

    def test_orchestrator_completed_normalizes_to_active(self) -> None:
        registry = AgentRegistry()

        registry.update("orchestrator", "completed")

        self.assertEqual(registry.snapshot()["orchestrator"], "active")


if __name__ == "__main__":
    unittest.main()
