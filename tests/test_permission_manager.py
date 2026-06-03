import unittest

from anubis.distributed import (
    AgentType,
    PermissionManager,
    PermissionedToolIntegrationLayer,
    ToolCategory,
    ToolExecutionContext,
    ToolGatekeeper,
    ToolPermissionStatus,
)


class RecordingDelegate:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, tool, tool_input=None):
        payload = dict(tool_input or {})
        self.calls.append((tool, payload))
        return {
            "tool": tool,
            "input": payload,
            "output": "delegated",
            "success": True,
            "logs": ["delegate called"],
        }


def context(agent_type, *, sandboxed=True, allow_network=False):
    return ToolExecutionContext(
        agent_type=agent_type,
        task_id="task-001",
        sandboxed=sandboxed,
        sandbox_id="sandbox-001" if sandboxed else None,
        workspace="/workspace/task-001" if sandboxed else None,
        allow_network=allow_network,
    )


class PermissionManagerTest(unittest.TestCase):
    def test_planner_has_read_only_access(self) -> None:
        manager = PermissionManager()

        read = manager.check("read_file", context(AgentType.PLANNER))
        write = manager.check("write_file", context(AgentType.PLANNER))
        shell = manager.check("run_command", context(AgentType.PLANNER))

        self.assertTrue(read.approved)
        self.assertEqual(read.category, ToolCategory.FILESYSTEM)
        self.assertFalse(write.approved)
        self.assertEqual(write.reason, "tool is not explicitly allowed for role")
        self.assertFalse(shell.approved)

    def test_executor_gets_file_and_shell_only_when_sandboxed(self) -> None:
        manager = PermissionManager()

        self.assertTrue(manager.check("write_file", context(AgentType.EXECUTOR)).approved)
        self.assertTrue(manager.check("run_command", context(AgentType.EXECUTOR)).approved)
        self.assertFalse(manager.check("run_command", context(AgentType.EXECUTOR, sandboxed=False)).approved)
        self.assertEqual(
            manager.check("run_command", context(AgentType.EXECUTOR, sandboxed=False)).reason,
            "sandbox context is required",
        )

    def test_reviewer_gets_read_only_and_analysis_tools(self) -> None:
        manager = PermissionManager()

        self.assertTrue(manager.check("read_file", context(AgentType.REVIEWER)).approved)
        self.assertTrue(manager.check("search_codebase", context(AgentType.REVIEWER)).approved)
        self.assertFalse(manager.check("write_file", context(AgentType.REVIEWER)).approved)
        self.assertFalse(manager.check("run_command", context(AgentType.REVIEWER)).approved)

    def test_git_and_network_are_denied_by_default(self) -> None:
        manager = PermissionManager()

        git = manager.check("git_commit", context(AgentType.EXECUTOR))
        network = manager.check("http_get", context(AgentType.EXECUTOR, allow_network=True))

        self.assertFalse(git.approved)
        self.assertEqual(git.reason, "tool is not explicitly allowed for role")
        self.assertFalse(network.approved)
        self.assertEqual(network.reason, "tool is not explicitly allowed for role")

    def test_unknown_tools_and_unknown_roles_are_denied(self) -> None:
        manager = PermissionManager()

        unknown_tool = manager.check("launch_missiles", context(AgentType.EXECUTOR))
        unknown_role = manager.check("read_file", context("intern"))

        self.assertFalse(unknown_tool.approved)
        self.assertEqual(unknown_tool.reason, "tool is not registered")
        self.assertFalse(unknown_role.approved)
        self.assertEqual(unknown_role.reason, "agent role has no permissions")

    def test_tool_gatekeeper_records_approval_history(self) -> None:
        gatekeeper = ToolGatekeeper()

        first = gatekeeper.approve("read_file", context(AgentType.PLANNER))
        second = gatekeeper.approve("write_file", context(AgentType.PLANNER))

        self.assertTrue(first.approved)
        self.assertFalse(second.approved)
        self.assertEqual(gatekeeper.history(), (first, second))

    def test_permissioned_tool_integration_denies_before_delegate(self) -> None:
        delegate = RecordingDelegate()
        layer = PermissionedToolIntegrationLayer(
            delegate=delegate,
            context=context(AgentType.PLANNER),
        )

        result = layer.execute("write_file", {"path": "/workspace/task-001/file.txt"})

        self.assertFalse(result["success"])
        self.assertEqual(result["permission"]["status"], ToolPermissionStatus.DENIED.value)
        self.assertEqual(delegate.calls, [])

    def test_permissioned_tool_integration_approves_then_delegates(self) -> None:
        delegate = RecordingDelegate()
        layer = PermissionedToolIntegrationLayer(
            delegate=delegate,
            context=context(AgentType.EXECUTOR),
        )

        result = layer.execute("run_command", {"cmd": "pwd"})

        self.assertTrue(result["success"])
        self.assertEqual(result["permission"]["status"], ToolPermissionStatus.APPROVED.value)
        self.assertEqual(delegate.calls, [("run_command", {"cmd": "pwd"})])


if __name__ == "__main__":
    unittest.main()
