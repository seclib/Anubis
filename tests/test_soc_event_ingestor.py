import json
import tempfile
import unittest
from pathlib import Path

from anubis.distributed import (
    AgentType,
    AuditLogger,
    CentralSOCEventCollector,
    EventType,
    ExecutionLogEntry,
    FileAccessAction,
    FileAccessAuditEntry,
    FileAccessDecision,
    NetworkAuditEntry,
    NetworkDecision,
    NetworkRequest,
    OrchestrationEvent,
    PermissionDecision,
    SOCEventStore,
    SOCEventType,
    SOCIngestionError,
    SOCRequiredIngestionGate,
    SOCStreamingPipeline,
    SandboxExecutionResult,
    ToolPermissionStatus,
)


class SOCEventIngestorTest(unittest.TestCase):
    def test_collector_normalizes_raw_dict_to_required_soc_shape(self) -> None:
        collector = CentralSOCEventCollector()

        event = collector.ingest(
            {"payload": {"decision": "approve"}},
            agent_id="reviewer-1",
            task_id="task-001",
            event_type=SOCEventType.AGENT_ACTION,
        )

        payload = event.to_dict()
        self.assertIn("timestamp", payload)
        self.assertEqual(payload["agent_id"], "reviewer-1")
        self.assertEqual(payload["task_id"], "task-001")
        self.assertEqual(payload["event_type"], "agent_action")
        self.assertEqual(payload["payload"]["decision"], "approve")
        self.assertEqual(payload["sequence"], 1)

    def test_ingests_agent_tool_file_network_and_error_sources(self) -> None:
        collector = CentralSOCEventCollector()
        audit = AuditLogger().log_agent_decision(task_id="task-001", agent_id="planner-1", decision="plan")
        tool_log = ExecutionLogEntry(step_id="step-1", tool="run_command", success=True, message="ok")
        file_log = FileAccessAuditEntry(
            task_id="task-001",
            action=FileAccessAction.READ,
            requested_path="/workspace/task-001/a.py",
            decision=FileAccessDecision.ALLOW,
        )
        network_log = NetworkAuditEntry(
            task_id="task-001",
            url="https://example.com",
            host="example.com",
            decision=NetworkDecision.ALLOW,
            reason="approved",
        )

        collector.ingest(audit)
        collector.ingest(tool_log, agent_id="executor-1", task_id="task-001")
        collector.ingest(file_log, agent_id="filesystem-jail")
        collector.ingest(network_log, agent_id="network-proxy")
        collector.ingest_system_error(RuntimeError("boom"), agent_id="sandbox-runtime", task_id="task-001")

        self.assertEqual([event.event_type for event in collector.events()], [
            "agent_action",
            "tool_execution",
            "file_access",
            "network_request",
            "system_error",
        ])
        self.assertEqual(collector.events()[-1].payload["error_type"], "RuntimeError")

    def test_normalizes_orchestration_permission_sandbox_and_network_request_events(self) -> None:
        collector = CentralSOCEventCollector()
        orchestration = OrchestrationEvent(
            event_type=EventType.TASK_ASSIGNED,
            task_id="task-001",
            agent_id="executor-1",
            message="assigned",
        )
        permission = PermissionDecision(
            status=ToolPermissionStatus.DENIED,
            tool="git_commit",
            agent_type=AgentType.EXECUTOR.value,
            reason="tool not allowed",
        )
        sandbox = SandboxExecutionResult(tool="run_command", success=False, error="timeout", sandbox_id="sandbox-1")
        request = NetworkRequest(task_id="task-001", url="https://example.com")

        collector.ingest(orchestration)
        collector.ingest(permission, task_id="task-001")
        collector.ingest(sandbox, agent_id="sandbox-runtime", task_id="task-001")
        collector.ingest(request, agent_id="network-proxy")

        events = collector.events()
        self.assertEqual(events[0].event_type, "orchestration_event")
        self.assertEqual(events[0].payload["event_type"], "task_assigned")
        self.assertEqual(events[1].event_type, "security_event")
        self.assertEqual(events[1].payload["status"], "denied")
        self.assertEqual(events[2].event_type, "tool_execution")
        self.assertEqual(events[2].payload["error"], "timeout")
        self.assertEqual(events[3].event_type, "network_request")
        self.assertEqual(events[3].payload["url"], "https://example.com")

    def test_streaming_pipeline_fans_out_events_without_batch_delay(self) -> None:
        received = []
        pipeline = SOCStreamingPipeline(max_workers=2)
        pipeline.subscribe(received.append)
        collector = CentralSOCEventCollector(pipeline=pipeline)

        event = collector.ingest({"payload": {"action": "execute"}}, agent_id="executor-1", task_id="task-001", event_type="execution_step")
        pipeline.drain(timeout=1)

        self.assertEqual(pipeline.published(), (event,))
        self.assertEqual(received, [event])

    def test_store_persists_normalized_jsonl_and_queries_by_type(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = SOCEventStore(Path(root) / "soc.jsonl")
            collector = CentralSOCEventCollector(store=store)

            collector.ingest({"payload": {"tool": "read_file"}}, agent_id="executor-1", task_id="task-001", event_type="tool_execution")
            collector.ingest({"payload": {"url": "https://example.com"}}, agent_id="network-proxy", task_id="task-002", event_type="network_request")

            network_events = collector.query(event_type=SOCEventType.NETWORK_REQUEST)
            rows = [json.loads(line) for line in (Path(root) / "soc.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual(len(network_events), 1)
            self.assertEqual(network_events[0].task_id, "task-002")
            self.assertEqual(rows[0]["event_type"], "tool_execution")
            self.assertEqual(rows[1]["sequence"], 2)

    def test_required_ingestion_gate_rejects_unsupported_event_sources(self) -> None:
        collector = CentralSOCEventCollector()
        gate = SOCRequiredIngestionGate(collector)

        with self.assertRaises(SOCIngestionError):
            gate.ingest_or_raise(object(), agent_id="agent-1", task_id="task-001")


if __name__ == "__main__":
    unittest.main()
