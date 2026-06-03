import unittest

from anubis.distributed import (
    AtomicCommitSpec,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    GitAgent,
    GitAutonomyRequest,
    GitStage,
)


DIFF_OUTPUT = """diff --git a/api/auth.py b/api/auth.py
index 1111111..2222222 100644
--- a/api/auth.py
+++ b/api/auth.py
@@ -1 +1,2 @@
-old
+new
+extra
diff --git a/web/Login.tsx b/web/Login.tsx
index 3333333..4444444 100644
--- a/web/Login.tsx
+++ b/web/Login.tsx
@@ -1 +1 @@
-old
+new
"""


class RecordingGitExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_push: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        type(self).calls.append((step_id, tool, tool_input))

        if tool == "git_diff":
            return ExecutionResult(step_id=step_id, success=True, output=DIFF_OUTPUT, logs=("diff",))
        if tool == "run_command" and "git push" in tool_input.get("cmd", "") and type(self).fail_push:
            return ExecutionResult(step_id=step_id, success=False, output="push failed", logs=("push failed",))
        return ExecutionResult(
            step_id=step_id,
            success=True,
            output=f"ran {tool_input.get('cmd', tool)}",
            logs=("ok",),
        )


class GitAgentTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RecordingGitExecutor.calls = []
        RecordingGitExecutor.fail_push = False
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def agent(self) -> GitAgent:
        return GitAgent(
            executor_pool=ExecutorWorkerPool(
                max_workers=1,
                executor_factory=RecordingGitExecutor,
                event_bus=self.event_bus,
            ),
            event_bus=self.event_bus,
        )

    async def test_git_agent_creates_branch_atomic_commits_and_pushes(self) -> None:
        agent = self.agent()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await agent.run(
            GitAutonomyRequest(
                task_id="Feature Login!",
                description="add login endpoint and frontend page",
                repo_path="/repos/anubis",
                repo_id="anubis",
                atomic_commits=(
                    AtomicCommitSpec(paths=("api/auth.py",), kind="feat", scope="api"),
                    AtomicCommitSpec(paths=("web/Login.tsx",), kind="feat", scope="web"),
                ),
            )
        )
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, GitStage.PUSHED)
        self.assertEqual(result.branch.name, "anubis/task/feature-login")
        self.assertEqual(result.diff.changed_files, ("api/auth.py", "web/Login.tsx"))
        self.assertEqual([commit.message for commit in result.commits], [
            "feat(api): add login endpoint and frontend page",
            "feat(web): add login endpoint and frontend page",
        ])

        tool_calls = [(tool, data["cmd"] if tool == "run_command" else "") for _id, tool, data in RecordingGitExecutor.calls]
        self.assertEqual(tool_calls[0], ("run_command", "git checkout -B anubis/task/feature-login"))
        self.assertEqual(tool_calls[1][0], "git_diff")
        self.assertIn(("run_command", "git add -- api/auth.py"), tool_calls)
        self.assertIn(("run_command", "git commit -m 'feat(api): add login endpoint and frontend page'"), tool_calls)
        self.assertIn(("run_command", "git push -u origin anubis/task/feature-login"), tool_calls)
        push_call = next(data for _id, tool, data in RecordingGitExecutor.calls if tool == "run_command" and "git push" in data["cmd"])
        self.assertTrue(push_call["allow_network"])
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_git_agent_stops_when_push_fails(self) -> None:
        RecordingGitExecutor.fail_push = True
        agent = self.agent()

        result = await agent.run(
            GitAutonomyRequest(
                task_id="feature-api-auth",
                description="fix api auth endpoint",
                repo_path="/repos/anubis",
                repo_id="api",
                changed_paths=("api/auth.py",),
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.stage, GitStage.FAILED)
        self.assertEqual(result.error, "push failed")
        self.assertIsNotNone(result.push_result)

    def test_diff_analysis_flags_sensitive_large_changes(self) -> None:
        agent = self.agent()
        diff = agent.analyze_diff(
            "diff --git a/package.json b/package.json\n"
            + "\n".join(f"+line {index}" for index in range(10))
        )

        self.assertEqual(diff.changed_files, ("package.json",))
        self.assertEqual(diff.risk, "high")
        self.assertEqual(diff.additions, 10)

    def test_semantic_commit_message_is_deterministic(self) -> None:
        agent = self.agent()
        request = GitAutonomyRequest(
            task_id="x",
            description="fix flaky distributed scheduler retries",
            repo_id="scheduler",
        )

        message = agent.semantic_commit_message(request, AtomicCommitSpec(kind="fix"), 1)

        self.assertEqual(message, "fix(scheduler): fix flaky distributed scheduler retries")


if __name__ == "__main__":
    unittest.main()
