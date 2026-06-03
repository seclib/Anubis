import json
import os
import tempfile
import unittest
from pathlib import Path

from anubis.distributed import (
    ExecutionStep,
    ExecutorAgent,
    IsolatedToolExecutor,
    ResourceLimits,
    SandboxedExecutorAgent,
    SandboxRuntime,
    SandboxRuntimeConfig,
    SandboxedToolIntegrationLayer,
)


class SandboxRuntimeTest(unittest.TestCase):
    def runtime(self, root: str, **limits) -> tuple[SandboxRuntime, IsolatedToolExecutor]:
        runtime = SandboxRuntime(
            SandboxRuntimeConfig(
                root_dir=root,
                default_limits=ResourceLimits(**({"timeout_seconds": 2.0, "cpu_seconds": 2, "memory_mb": 256} | limits)),
            )
        )
        return runtime, IsolatedToolExecutor(runtime=runtime)

    def test_sandbox_runtime_creates_ephemeral_workspace_per_task(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime = SandboxRuntime(SandboxRuntimeConfig(root_dir=root))

            first = runtime.create("task-001")
            second = runtime.create("task-001")

            self.assertNotEqual(first.workspace, second.workspace)
            self.assertTrue(first.workspace.exists())
            self.assertTrue(second.workspace.exists())
            self.assertTrue(str(first.workspace).startswith(str(Path(root).resolve())))

    def test_isolated_executor_blocks_host_path_access(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            _runtime, executor = self.runtime(root)

            result = executor.execute(task_id="task-escape", tool="read_file", tool_input={"path": "/etc/passwd"})

            self.assertFalse(result.success)
            self.assertIn("absolute host paths are not allowed", result.error)

    def test_file_operations_are_confined_to_sandbox_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime, executor = self.runtime(root)
            context = runtime.create("task-files")

            write = executor.execute(
                task_id="task-files",
                tool="write_file",
                tool_input={"path": "src/result.txt", "content": "sandboxed"},
                context=context,
            )
            read = executor.execute(
                task_id="task-files",
                tool="read_file",
                tool_input={"path": "src/result.txt"},
                context=context,
            )

            self.assertTrue(write.success)
            self.assertTrue(read.success)
            self.assertEqual(read.output, "sandboxed")
            self.assertTrue((context.workspace / "src/result.txt").exists())

    def test_each_tool_execution_runs_in_separate_worker_process(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime, executor = self.runtime(root)
            context = runtime.create("task-process")

            first = executor.execute(task_id="task-process", tool="run_command", tool_input={"cmd": "pwd"}, context=context)
            second = executor.execute(task_id="task-process", tool="run_command", tool_input={"cmd": "pwd"}, context=context)

            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertIsNotNone(first.worker_pid)
            self.assertIsNotNone(second.worker_pid)
            self.assertNotEqual(first.worker_pid, os.getpid())
            self.assertNotEqual(first.worker_pid, second.worker_pid)

    def test_timeout_enforcement_kills_long_running_execution(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime, executor = self.runtime(root, timeout_seconds=0.2, cpu_seconds=1)
            context = runtime.create("task-timeout", ResourceLimits(timeout_seconds=0.2, cpu_seconds=1, memory_mb=256))

            result = executor.execute(
                task_id="task-timeout",
                tool="run_command",
                tool_input={"cmd": "sleep 2"},
                context=context,
            )

            self.assertFalse(result.success)
            self.assertTrue(result.timed_out)
            self.assertIn("timed out", result.error)

    def test_search_codebase_reads_only_sandbox_files(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime, executor = self.runtime(root)
            context = runtime.create("task-search")
            executor.execute(
                task_id="task-search",
                tool="write_file",
                tool_input={"path": "app.py", "content": "def secure_runtime():\n    return True\n"},
                context=context,
            )

            result = executor.execute(
                task_id="task-search",
                tool="search_codebase",
                tool_input={"query": "secure_runtime"},
                context=context,
            )

            self.assertTrue(result.success)
            payload = json.loads(result.output)
            self.assertEqual(payload["matches"][0]["path"], "app.py")

    def test_executor_agent_can_use_sandboxed_tool_layer(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime, executor = self.runtime(root)
            tools = SandboxedToolIntegrationLayer(executor, task_id="executor-task")
            agent = ExecutorAgent(tools=tools)

            result = agent.execute(ExecutionStep("step-001", "run_command", {"cmd": "pwd"}))

            self.assertTrue(result.success)
            self.assertIn("executor-task", result.output)

    def test_sandboxed_executor_agent_forces_sandboxed_tools(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            runtime, executor = self.runtime(root)
            agent = SandboxedExecutorAgent(executor=executor, task_id="facade-task")

            result = agent.execute(ExecutionStep("step-002", "run_command", {"cmd": "pwd"}))

            self.assertTrue(result.success)
            self.assertIn(str(runtime.root), result.output)
            self.assertIn("facade-task", result.output)


if __name__ == "__main__":
    unittest.main()
