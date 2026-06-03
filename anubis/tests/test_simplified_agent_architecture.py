import unittest

from anubis.distributed.agent_architecture import (
    PlatformService,
    simplified_agent_architecture,
    target_for_legacy_agent,
)
from anubis.distributed.contracts import AgentType


class SimplifiedAgentArchitectureTest(unittest.TestCase):
    def test_architecture_has_only_three_agent_roles(self) -> None:
        architecture = simplified_agent_architecture()

        self.assertEqual(
            {role.agent_type for role in architecture.roles},
            {AgentType.PLANNER, AgentType.EXECUTOR, AgentType.REVIEWER},
        )
        self.assertEqual(len(architecture.roles), 3)

    def test_orchestration_and_memory_are_services_not_agents(self) -> None:
        architecture = simplified_agent_architecture()

        self.assertIn(PlatformService.ORCHESTRATION, architecture.platform_services)
        self.assertIn(PlatformService.MEMORY, architecture.platform_services)
        self.assertEqual(target_for_legacy_agent("orchestrator_agent"), PlatformService.ORCHESTRATION)
        self.assertEqual(target_for_legacy_agent("memory_agent"), PlatformService.MEMORY)

    def test_duplicate_reasoning_agents_have_canonical_targets(self) -> None:
        self.assertEqual(target_for_legacy_agent("coder_agent"), AgentType.EXECUTOR)
        self.assertEqual(target_for_legacy_agent("tester_agent"), AgentType.EXECUTOR)
        self.assertEqual(target_for_legacy_agent("debugger_agent"), AgentType.REVIEWER)
        self.assertEqual(target_for_legacy_agent("critic_agent"), AgentType.REVIEWER)
        self.assertEqual(target_for_legacy_agent("meta_cognition_agent"), AgentType.REVIEWER)

    def test_migration_plan_is_incremental_and_non_destructive(self) -> None:
        steps = simplified_agent_architecture().migration_steps

        self.assertTrue(any("Freeze new feature work" in step for step in steps))
        self.assertTrue(any("Remove legacy modules once" in step for step in steps))
        self.assertTrue(any("parity tests" in step for step in steps))


if __name__ == "__main__":
    unittest.main()
