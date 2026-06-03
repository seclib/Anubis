import unittest

from anubis_cli_mvp.agents import AgentManager
from anubis_cli_mvp.dsl import CommandParser
from anubis_cli_mvp.swarm import SwarmEngine


class AnubisCliMvpTest(unittest.TestCase):
    def test_parser_keeps_raw_arguments(self) -> None:
        command = CommandParser().parse('/build "minimal cli" --fast')

        self.assertEqual(command.name, "/build")
        self.assertEqual(command.args, ["minimal cli", "--fast"])
        self.assertEqual(command.raw_args, '"minimal cli" --fast')

    def test_agent_manager_marks_completed_after_run(self) -> None:
        agents = AgentManager()

        result = agents.run("builder", lambda: "done")

        self.assertEqual(result, "done")
        self.assertEqual(agents.states["builder"], "completed")
        self.assertEqual(agents.states["orchestrator"], "active")

    def test_swarm_completes_core_agents(self) -> None:
        agents = AgentManager()
        result = SwarmEngine(agents).run("build app")

        self.assertIn("aggregation: completed", result)
        self.assertEqual(agents.states["builder"], "completed")
        self.assertEqual(agents.states["researcher"], "completed")
        self.assertEqual(agents.states["analyst"], "completed")
        self.assertEqual(agents.states["orchestrator"], "active")


if __name__ == "__main__":
    unittest.main()
