from datetime import datetime, timezone
import unittest

from anubis.distributed import (
    AnomalyDetectionEngine,
    BehaviorBaseline,
    BehaviorScoringSystem,
    KillSwitchState,
    KillSwitchController,
    RiskClassification,
    RiskClassifier,
    RiskScore,
    SOCEvent,
    SOCResponseActionType,
    SOCResponseEngine,
    SOCResponseRiskLevel,
)


def soc_event(agent_id, task_id, event_type, payload):
    return SOCEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        payload=payload,
    )


class SOCResponseEngineTest(unittest.TestCase):
    def classification(self, score):
        event = soc_event("executor-1", "task-001", "tool_execution", {"tool": "read_file", "success": True})
        return RiskClassification(event=event, score=score, findings=())

    def anomaly_classification(self, event):
        detector = AnomalyDetectionEngine(RiskClassifier(BehaviorScoringSystem(BehaviorBaseline.default())))
        return detector.analyze(event)

    def test_low_risk_logs_only(self) -> None:
        engine = SOCResponseEngine()

        result = engine.respond(self.classification(RiskScore.SAFE))

        self.assertEqual(result.plan.risk_level, SOCResponseRiskLevel.LOW)
        self.assertEqual([action.action_type for action in result.actions], [SOCResponseActionType.LOG_ONLY])
        self.assertFalse(engine.enforcement.is_agent_throttled("executor-1"))
        self.assertFalse(engine.enforcement.is_task_paused("task-001"))

    def test_medium_risk_throttles_agent_and_increases_monitoring(self) -> None:
        engine = SOCResponseEngine()
        classification = self.anomaly_classification(
            soc_event("executor-1", "task-001", "system_error", {"error_type": "RuntimeError", "message": "boom"})
        )

        result = engine.respond(classification)

        self.assertEqual(result.plan.risk_level, SOCResponseRiskLevel.MEDIUM)
        self.assertEqual([action.action_type for action in result.actions], [
            SOCResponseActionType.THROTTLE_AGENT,
            SOCResponseActionType.INCREASE_MONITORING,
        ])
        self.assertTrue(engine.enforcement.is_agent_throttled("executor-1"))
        state = engine.enforcement.state()
        self.assertEqual(state.monitored_agents, ("executor-1",))

    def test_high_risk_pauses_task_and_isolates_sandbox(self) -> None:
        engine = SOCResponseEngine()
        classification = self.anomaly_classification(
            soc_event(
                "executor-1",
                "task-001",
                "file_access",
                {"action": "write", "requested_path": "/workspace/task-001/a.py", "decision": "allow", "sandbox_id": "sandbox-1"},
            )
        )
        # Force high risk without needing repeated mass-file setup.
        classification = RiskClassification(event=classification.event, score=RiskScore.DANGEROUS, findings=classification.findings)

        result = engine.respond(classification)

        self.assertEqual(result.plan.risk_level, SOCResponseRiskLevel.HIGH)
        self.assertEqual([action.action_type for action in result.actions], [
            SOCResponseActionType.PAUSE_TASK,
            SOCResponseActionType.ISOLATE_SANDBOX,
        ])
        self.assertTrue(engine.enforcement.is_task_paused("task-001"))
        self.assertTrue(engine.enforcement.is_sandbox_isolated("sandbox-1"))

    def test_critical_risk_triggers_kill_switch_and_freezes_state(self) -> None:
        kill_switch = KillSwitchController()
        engine = SOCResponseEngine(kill_switch=kill_switch)
        classification = self.anomaly_classification(
            soc_event("planner-1", "task-001", "tool_execution", {"tool": "run_command", "success": True})
        )

        result = engine.respond(classification)

        self.assertEqual(result.plan.risk_level, SOCResponseRiskLevel.CRITICAL)
        self.assertEqual([action.action_type for action in result.actions], [
            SOCResponseActionType.TRIGGER_KILL_SWITCH,
            SOCResponseActionType.FREEZE_SYSTEM_STATE,
        ])
        self.assertEqual(kill_switch.state, KillSwitchState.RECOVERY)
        self.assertIsNotNone(result.kill_switch_status)
        snapshot = kill_switch.recovery_manager.snapshot()
        self.assertIsNotNone(snapshot)
        self.assertIn("soc_response", snapshot.frozen_state)

    def test_reversible_actions_release_agent_task_and_sandbox(self) -> None:
        engine = SOCResponseEngine()
        high = RiskClassification(
            event=soc_event("executor-1", "task-001", "tool_execution", {"tool": "run_command", "sandbox_id": "sandbox-1"}),
            score=RiskScore.DANGEROUS,
            findings=(),
        )
        medium = RiskClassification(
            event=soc_event("executor-1", "task-001", "system_error", {"message": "warn"}),
            score=RiskScore.SUSPICIOUS,
            findings=(),
        )

        engine.respond(medium)
        engine.respond(high)
        engine.release_agent("executor-1")
        engine.resume_task("task-001")
        engine.release_sandbox("sandbox-1")

        self.assertFalse(engine.enforcement.is_agent_throttled("executor-1"))
        self.assertFalse(engine.enforcement.is_task_paused("task-001"))
        self.assertFalse(engine.enforcement.is_sandbox_isolated("sandbox-1"))

    def test_response_engine_records_results_for_realtime_sink_usage(self) -> None:
        engine = SOCResponseEngine()

        engine.ingest(self.classification(RiskScore.SAFE))

        self.assertEqual(len(engine.results()), 1)
        self.assertEqual(engine.results()[0].plan.risk_level, SOCResponseRiskLevel.LOW)


if __name__ == "__main__":
    unittest.main()
