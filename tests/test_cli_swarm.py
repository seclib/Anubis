import unittest

from cli.agents import AgentRegistry
from cli.swarm import SwarmEngine


class SwarmEngineTest(unittest.TestCase):
    def test_landing_page_goal_uses_ui_profile(self) -> None:
        agents = AgentRegistry()
        result = SwarmEngine(agents).run("build a landing page")

        rendered = result.render()
        self.assertIn("- builder -> UI structure", rendered)
        self.assertIn("- researcher -> design inspiration", rendered)
        self.assertIn("- analyst -> optimization", rendered)
        self.assertIn("aggregate: combined swarm result prepared", rendered)

    def test_swarm_updates_agent_states(self) -> None:
        agents = AgentRegistry()

        SwarmEngine(agents).run("debug backend service")

        snapshot = agents.snapshot()
        self.assertEqual(snapshot["builder"], "completed")
        self.assertEqual(snapshot["researcher"], "completed")
        self.assertEqual(snapshot["analyst"], "completed")
        self.assertEqual(snapshot["orchestrator"], "active")


if __name__ == "__main__":
    unittest.main()
