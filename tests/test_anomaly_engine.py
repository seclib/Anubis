from datetime import datetime, timezone
import unittest

from anubis.distributed import (
    AnomalyCode,
    AnomalyDetectionEngine,
    BehaviorBaseline,
    BehaviorScoringSystem,
    CentralSOCEventCollector,
    RiskClassifier,
    RiskScore,
    SOCEvent,
    SOCStreamingPipeline,
)


def event(agent_id, task_id, event_type, payload):
    return SOCEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        payload=payload,
    )


class AnomalyEngineTest(unittest.TestCase):
    def engine(self, **baseline_overrides):
        baseline = BehaviorBaseline.default()
        if baseline_overrides:
            baseline = BehaviorBaseline(
                allowed_tools_by_role=baseline_overrides.get("allowed_tools_by_role", baseline.allowed_tools_by_role),
                allowed_event_types_by_role=baseline_overrides.get("allowed_event_types_by_role", baseline.allowed_event_types_by_role),
                allowlisted_domains=baseline_overrides.get("allowlisted_domains", baseline.allowlisted_domains),
                forbidden_domains=baseline_overrides.get("forbidden_domains", baseline.forbidden_domains),
                repeated_failure_threshold=baseline_overrides.get("repeated_failure_threshold", baseline.repeated_failure_threshold),
                repeated_action_threshold=baseline_overrides.get("repeated_action_threshold", baseline.repeated_action_threshold),
                mass_file_write_threshold=baseline_overrides.get("mass_file_write_threshold", baseline.mass_file_write_threshold),
            )
        return AnomalyDetectionEngine(RiskClassifier(BehaviorScoringSystem(baseline)))

    def test_safe_executor_tool_usage_scores_zero(self) -> None:
        engine = self.engine()

        result = engine.analyze(event("executor-1", "task-001", "tool_execution", {"tool": "read_file", "success": True}))

        self.assertEqual(result.score, RiskScore.SAFE)
        self.assertEqual(result.findings, ())

    def test_repeated_failures_are_dangerous(self) -> None:
        engine = self.engine(repeated_failure_threshold=3)

        events = [
            event("executor-1", "task-001", "tool_execution", {"tool": "run_command", "success": False}),
            event("executor-1", "task-001", "tool_execution", {"tool": "run_command", "success": False}),
            event("executor-1", "task-001", "tool_execution", {"tool": "run_command", "success": False}),
        ]
        results = engine.analyze_many(events)

        self.assertEqual(results[-1].score, RiskScore.DANGEROUS)
        self.assertEqual(results[-1].findings[0].code, AnomalyCode.REPEATED_FAILURES)

    def test_loop_like_repeated_execution_is_critical(self) -> None:
        engine = self.engine(repeated_action_threshold=3)

        results = [
            engine.analyze(event("executor-1", "task-001", "execution_step", {"action": "retry compile", "success": True}))
            for _ in range(3)
        ]

        self.assertEqual(results[-1].score, RiskScore.CRITICAL)
        self.assertEqual(results[-1].findings[0].code, AnomalyCode.INFINITE_LOOP)

    def test_unexpected_tool_usage_detects_role_violation(self) -> None:
        engine = self.engine()

        result = engine.analyze(event("reviewer-1", "task-001", "tool_execution", {"tool": "run_command", "success": True}))

        codes = {finding.code for finding in result.findings}
        self.assertIn(AnomalyCode.UNEXPECTED_TOOL_USAGE, codes)
        self.assertIn(AnomalyCode.ROLE_VIOLATION, codes)
        self.assertGreaterEqual(result.score, RiskScore.DANGEROUS)

    def test_unauthorized_path_access_is_critical(self) -> None:
        engine = self.engine()

        result = engine.analyze(
            event(
                "executor-1",
                "task-001",
                "file_access",
                {"action": "read", "requested_path": "/etc/passwd", "decision": "deny"},
            )
        )

        self.assertEqual(result.score, RiskScore.CRITICAL)
        self.assertEqual(result.findings[0].code, AnomalyCode.UNAUTHORIZED_PATH_ACCESS)

    def test_mass_file_modification_is_dangerous(self) -> None:
        engine = self.engine(mass_file_write_threshold=3)

        results = [
            engine.analyze(
                event(
                    "executor-1",
                    "task-001",
                    "file_access",
                    {"action": "write", "requested_path": f"/workspace/task-001/file-{index}.py", "decision": "allow"},
                )
            )
            for index in range(3)
        ]

        self.assertEqual(results[-1].score, RiskScore.DANGEROUS)
        self.assertEqual(results[-1].findings[0].code, AnomalyCode.MASS_FILE_MODIFICATION)

    def test_planner_execution_and_executor_planning_are_detected(self) -> None:
        engine = self.engine()

        planner_result = engine.analyze(event("planner-1", "task-001", "tool_execution", {"tool": "run_command", "success": True}))
        executor_result = engine.analyze(event("executor-1", "task-002", "agent_action", {"decision": "decompose plan into dependency steps"}))

        self.assertIn(AnomalyCode.PLANNER_EXECUTING, {finding.code for finding in planner_result.findings})
        self.assertIn(AnomalyCode.EXECUTOR_PLANNING, {finding.code for finding in executor_result.findings})

    def test_network_forbidden_and_unexpected_domains_are_classified(self) -> None:
        engine = self.engine(allowlisted_domains=frozenset({"example.com"}))

        forbidden = engine.analyze(event("executor-1", "task-001", "network_request", {"url": "http://localhost:8000", "decision": "deny"}))
        unexpected = engine.analyze(event("executor-1", "task-001", "network_request", {"url": "https://unknown.test/api", "decision": "allow"}))

        self.assertEqual(forbidden.score, RiskScore.CRITICAL)
        self.assertIn(AnomalyCode.FORBIDDEN_DOMAIN, {finding.code for finding in forbidden.findings})
        self.assertEqual(unexpected.score, RiskScore.DANGEROUS)
        self.assertIn(AnomalyCode.UNEXPECTED_EXTERNAL_CALL, {finding.code for finding in unexpected.findings})

    def test_streaming_soc_pipeline_can_feed_anomaly_engine(self) -> None:
        pipeline = SOCStreamingPipeline(max_workers=1)
        detector = self.engine()
        pipeline.subscribe(detector.ingest)
        collector = CentralSOCEventCollector(pipeline=pipeline)

        collector.ingest(
            {"payload": {"requested_path": "/root/.ssh/id_rsa", "decision": "deny", "action": "read"}},
            agent_id="executor-1",
            task_id="task-001",
            event_type="file_access",
        )
        pipeline.drain(timeout=1)

        findings = detector.findings(minimum_score=RiskScore.CRITICAL)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, AnomalyCode.UNAUTHORIZED_PATH_ACCESS)


if __name__ == "__main__":
    unittest.main()
