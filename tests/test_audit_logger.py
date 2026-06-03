import json
import tempfile
import unittest
from pathlib import Path

from anubis.distributed import (
    AuditActionType,
    AuditLogger,
    AuditLogStore,
    AuditResult,
    ObservabilityDashboardBackend,
)


class AuditLoggerTest(unittest.TestCase):
    def test_logs_tool_calls_with_required_structured_fields(self) -> None:
        logger = AuditLogger()

        record = logger.log_tool_call(
            task_id="task-001",
            agent_id="executor-1",
            tool="run_command",
            success=True,
            step_id="step-1",
            details={"command": "pytest"},
        )

        payload = record.to_dict()
        self.assertIn("timestamp", payload)
        self.assertEqual(payload["task_id"], "task-001")
        self.assertEqual(payload["agent_id"], "executor-1")
        self.assertEqual(payload["action_type"], "tool_call")
        self.assertEqual(payload["result"], "success")
        self.assertEqual(payload["step_id"], "step-1")
        self.assertEqual(payload["details"]["command"], "pytest")

    def test_jsonl_store_persists_structured_logs(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            log_path = Path(root) / "audit.jsonl"
            logger = AuditLogger(store=AuditLogStore(log_path))

            logger.log_agent_decision(
                task_id="task-001",
                agent_id="planner-1",
                decision="decompose task",
                details={"steps": 3},
            )

            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action_type"], "agent_decision")
            self.assertEqual(rows[0]["result"], "info")
            self.assertEqual(rows[0]["details"]["steps"], 3)

    def test_trace_system_builds_full_execution_trace_per_task(self) -> None:
        logger = AuditLogger()

        logger.log_agent_decision(task_id="task-001", agent_id="planner-1", decision="plan")
        logger.log_execution_step(task_id="task-001", agent_id="executor-1", step_id="step-1", action="edit file", success=True)
        logger.log_tool_call(task_id="task-001", agent_id="executor-1", tool="write_file", success=True, step_id="step-1")
        logger.log_execution_step(task_id="task-001", agent_id="reviewer-1", step_id="verify-1", action="validate", success=True)

        trace = logger.trace_for_task("task-001")

        self.assertEqual(trace.task_id, "task-001")
        self.assertEqual(trace.trace_id, "trace-task-001")
        self.assertEqual([event.sequence for event in trace.events], [1, 2, 3, 4])
        self.assertFalse(trace.failed)
        self.assertEqual(trace.events[0].record.action_type, AuditActionType.AGENT_DECISION)

    def test_trace_marks_denied_or_failed_actions_as_failed(self) -> None:
        logger = AuditLogger()

        logger.log_file_access(
            task_id="task-001",
            agent_id="executor-1",
            path="/etc/passwd",
            operation="read",
            allowed=False,
            details={"reason": "outside workspace"},
        )

        trace = logger.trace_for_task("task-001")
        self.assertTrue(trace.failed)
        self.assertEqual(trace.events[0].record.result, AuditResult.DENIED)

    def test_dashboard_backend_queries_records_and_summary(self) -> None:
        logger = AuditLogger()
        backend = ObservabilityDashboardBackend(logger)
        logger.log_tool_call(task_id="task-001", agent_id="executor-1", tool="run_command", success=True)
        logger.log_tool_call(task_id="task-001", agent_id="executor-1", tool="write_file", success=False)
        logger.log_agent_decision(task_id="task-002", agent_id="reviewer-1", decision="reject", result=AuditResult.FAILURE)

        executor_records = backend.records(agent_id="executor-1")
        failures = backend.records(result="failure")
        summary = backend.summary().to_dict()
        task_trace = backend.task_trace("task-001")

        self.assertEqual(len(executor_records), 2)
        self.assertEqual(len(failures), 2)
        self.assertEqual(summary["total_records"], 3)
        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["action_counts"]["tool_call"], 2)
        self.assertEqual(summary["result_counts"]["failure"], 2)
        self.assertEqual(len(task_trace["events"]), 2)

    def test_query_filters_by_task_and_action_type(self) -> None:
        logger = AuditLogger()
        logger.log_file_access(task_id="task-001", agent_id="executor-1", path="/workspace/task-001/a.py", operation="read", allowed=True)
        logger.log_tool_call(task_id="task-001", agent_id="executor-1", tool="read_file", success=True)
        logger.log_file_access(task_id="task-002", agent_id="executor-2", path="/workspace/task-002/b.py", operation="write", allowed=True)

        records = logger.store.query(task_id="task-001", action_type=AuditActionType.FILE_ACCESS)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].action, "read")

    def test_rejects_missing_required_identity_fields(self) -> None:
        logger = AuditLogger()

        with self.assertRaises(ValueError):
            logger.log_tool_call(task_id="", agent_id="executor-1", tool="run_command", success=True)
        with self.assertRaises(ValueError):
            logger.log_tool_call(task_id="task-001", agent_id="", tool="run_command", success=True)


if __name__ == "__main__":
    unittest.main()
