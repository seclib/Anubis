from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from anubis.distributed import (
    AnomalyDetectionEngine,
    AttackExecutionResult,
    AttackExecutionStatus,
    AttackGenerationRequest,
    AttackGenerator,
    BehaviorBaseline,
    BehaviorScoringSystem,
    DefenseAnalyzer,
    DefenseGrade,
    KillSwitchController,
    RiskClassification,
    RiskClassifier,
    RiskScore,
    SandboxAttackRunner,
    SandboxRuntime,
    SandboxRuntimeConfig,
    SOCEvent,
    SOCResponseEngine,
)


def soc_event(agent_id, task_id, event_type, payload, *, timestamp=None):
    return SOCEvent(
        timestamp=timestamp or datetime.now(timezone.utc),
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        payload=payload,
    )


class DefenseAnalyzerTest(unittest.TestCase):
    def runner(self):
        root = tempfile.TemporaryDirectory()
        runtime = SandboxRuntime(SandboxRuntimeConfig(root_dir=root.name))
        return root, SandboxAttackRunner(runtime=runtime)

    def detector(self):
        return AnomalyDetectionEngine(RiskClassifier(BehaviorScoringSystem(BehaviorBaseline.default())))

    def test_analyzer_scores_fast_detected_and_contained_attack_as_pass(self) -> None:
        root, runner = self.runner()
        self.addCleanup(root.cleanup)
        scenario = AttackGenerator().generate(AttackGenerationRequest(task_id="red-team-001", max_scenarios=1))[0]
        attack_result = runner.run(scenario)
        started_at = attack_result.logs[0].created_at
        detection = self.detector().analyze(
            soc_event(
                "executor-1",
                "red-team-001",
                "file_access",
                {"action": "read", "requested_path": "/etc/passwd", "decision": "deny", "attack_id": attack_result.attack_id},
                timestamp=started_at + timedelta(milliseconds=25),
            )
        )
        response = SOCResponseEngine().respond(detection)

        report = DefenseAnalyzer().analyze(
            [attack_result],
            anomaly_results=[detection],
            response_results=[response],
            soc_events=[detection.event],
        )

        self.assertEqual(report.grade, DefenseGrade.PASS)
        self.assertTrue(report.passed)
        self.assertEqual(report.metrics.attacks_total, 1)
        self.assertEqual(report.metrics.attacks_contained, 1)
        self.assertEqual(report.metrics.false_negatives, 0)
        self.assertEqual(report.metrics.blocked_actions, 3)
        self.assertLessEqual(report.metrics.detection_speed_ms, 25)
        self.assertGreaterEqual(report.metrics.resilience_score, 85)

    def test_analyzer_counts_false_negative_when_attack_has_no_soc_detection(self) -> None:
        root, runner = self.runner()
        self.addCleanup(root.cleanup)
        scenario = AttackGenerator().generate(AttackGenerationRequest(task_id="red-team-002", max_scenarios=1))[0]
        attack_result = runner.run(scenario)

        report = DefenseAnalyzer().analyze([attack_result])

        self.assertEqual(report.grade, DefenseGrade.FAIL)
        self.assertEqual(report.metrics.false_negatives, 1)
        self.assertEqual(report.metrics.detection_rate, 0)
        self.assertIn("false_negatives_detected", {finding.code for finding in report.findings})
        self.assertIn("detection_speed_unavailable", {finding.code for finding in report.findings})

    def test_analyzer_detects_containment_gap_from_bypass_result(self) -> None:
        bypass = AttackExecutionResult(
            attack_id="attack_bypass",
            attack_type="logic_corruption",
            target="orchestrator",
            status=AttackExecutionStatus.BYPASS_DETECTED,
            success=False,
            sandbox_id="sandbox-1",
            system_response={"contained": False},
            bypass_detected=True,
        )
        detection = RiskClassification(
            event=soc_event("executor-1", "attack_bypass", "security_event", {"attack_id": "attack_bypass"}),
            score=RiskScore.DANGEROUS,
            findings=(),
        )

        report = DefenseAnalyzer().analyze([bypass], anomaly_results=[detection])

        self.assertEqual(report.metrics.attacks_contained, 0)
        self.assertEqual(report.metrics.false_negatives, 0)
        self.assertEqual(report.grade, DefenseGrade.FAIL)
        self.assertIn("containment_gap", {finding.code for finding in report.findings})

    def test_analyzer_collects_kill_switch_triggers_and_response_actions(self) -> None:
        root, runner = self.runner()
        self.addCleanup(root.cleanup)
        scenario = AttackGenerator().generate(AttackGenerationRequest(task_id="red-team-003", max_scenarios=1))[0]
        attack_result = runner.run(scenario)
        critical = self.detector().analyze(
            soc_event(
                "planner-1",
                "red-team-003",
                "tool_execution",
                {"tool": "run_command", "success": True, "attack_id": attack_result.attack_id},
                timestamp=attack_result.logs[0].created_at + timedelta(milliseconds=10),
            )
        )
        kill_switch = KillSwitchController()
        response = SOCResponseEngine(kill_switch=kill_switch).respond(critical)

        report = DefenseAnalyzer().analyze(
            [attack_result],
            anomaly_results=[critical],
            response_results=[response],
            kill_switch_statuses=[kill_switch.status()],
        )

        self.assertEqual(report.metrics.kill_switch_triggers, 2)
        self.assertEqual(report.metrics.blocked_actions, 2)
        self.assertEqual(report.metrics.false_negatives, 0)
        self.assertGreaterEqual(report.metrics.resilience_score, 85)

    def test_report_serializes_metrics_findings_and_source_results(self) -> None:
        root, runner = self.runner()
        self.addCleanup(root.cleanup)
        scenario = AttackGenerator().generate(AttackGenerationRequest(task_id="red-team-004", max_scenarios=1))[0]
        attack_result = runner.run(scenario)

        report = DefenseAnalyzer().analyze([attack_result])
        payload = report.to_dict()

        self.assertEqual(payload["metrics"]["attacks_total"], 1)
        self.assertEqual(payload["attack_results"][0]["attack_id"], attack_result.attack_id)
        self.assertGreaterEqual(len(payload["findings"]), 1)


if __name__ == "__main__":
    unittest.main()
