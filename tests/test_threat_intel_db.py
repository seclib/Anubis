from datetime import datetime, timezone
import unittest

from anubis.distributed import (
    AnomalyDetectionEngine,
    BehaviorBaseline,
    BehaviorScoringSystem,
    IncidentMemorySystem,
    IncidentVerdict,
    RiskClassifier,
    SOCEvent,
    SOCResponseEngine,
    ThreatIntelDB,
)


def soc_event(agent_id, task_id, event_type, payload):
    return SOCEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id=agent_id,
        task_id=task_id,
        event_type=event_type,
        payload=payload,
    )


def detector(**baseline_overrides):
    baseline = BehaviorBaseline.default()
    if baseline_overrides:
        baseline = BehaviorBaseline(
            allowed_tools_by_role=baseline.allowed_tools_by_role,
            allowed_event_types_by_role=baseline.allowed_event_types_by_role,
            allowlisted_domains=baseline.allowlisted_domains,
            forbidden_domains=baseline.forbidden_domains,
            repeated_failure_threshold=baseline_overrides.get("repeated_failure_threshold", baseline.repeated_failure_threshold),
            repeated_action_threshold=baseline_overrides.get("repeated_action_threshold", baseline.repeated_action_threshold),
            mass_file_write_threshold=baseline_overrides.get("mass_file_write_threshold", baseline.mass_file_write_threshold),
        )
    return AnomalyDetectionEngine(RiskClassifier(BehaviorScoringSystem(baseline)))


class ThreatIntelDBTest(unittest.TestCase):
    def test_incident_memory_stores_anomaly_response_and_metadata(self) -> None:
        anomaly = detector().analyze(soc_event("planner-1", "task-001", "tool_execution", {"tool": "run_command", "success": True}))
        response = SOCResponseEngine().respond(anomaly)
        db = ThreatIntelDB()

        incident = db.record_incident(anomaly, response=response, verdict=IncidentVerdict.TRUE_POSITIVE, notes="planner attempted shell")

        self.assertEqual(incident.classification, anomaly)
        self.assertEqual(incident.response, response)
        self.assertEqual(incident.verdict, IncidentVerdict.TRUE_POSITIVE)
        self.assertIn("planner attempted shell", incident.notes)
        self.assertIn("planner_executing", incident.pattern_text)

    def test_vector_memory_finds_similar_past_attacks(self) -> None:
        db = ThreatIntelDB()
        first = detector().analyze(soc_event("executor-1", "task-001", "file_access", {"action": "read", "requested_path": "/etc/passwd", "decision": "deny"}))
        similar = detector().analyze(soc_event("executor-2", "task-002", "file_access", {"action": "read", "requested_path": "/etc/shadow", "decision": "deny"}))
        unrelated = detector().analyze(soc_event("executor-3", "task-003", "network_request", {"url": "https://unknown.test", "decision": "allow"}))

        stored = db.record_incident(first, verdict=IncidentVerdict.TRUE_POSITIVE)
        db.record_incident(unrelated, verdict=IncidentVerdict.TRUE_POSITIVE)
        matches = db.similar_attacks(similar, limit=2)

        self.assertEqual(matches[0].incident.incident_id, stored.incident_id)
        self.assertGreater(matches[0].score, 0.0)

    def test_false_positive_feedback_raises_repeated_failure_threshold(self) -> None:
        db = ThreatIntelDB()
        detect = detector(repeated_failure_threshold=2)
        events = [
            soc_event("executor-1", "task-001", "tool_execution", {"tool": "run_command", "success": False}),
            soc_event("executor-1", "task-001", "tool_execution", {"tool": "run_command", "success": False}),
        ]
        classification = detect.analyze_many(events)[-1]
        incident = db.record_incident(classification)
        db.mark_false_positive(incident.incident_id, notes="expected flaky test retry")

        result = db.refine_detection_baseline(BehaviorBaseline.default())

        self.assertGreater(result.baseline.repeated_failure_threshold, BehaviorBaseline.default().repeated_failure_threshold)
        self.assertEqual(result.false_positive_count, 1)
        self.assertEqual(result.adjustments[0].field, "repeated_failure_threshold")

    def test_true_positive_feedback_lowers_loop_threshold(self) -> None:
        db = ThreatIntelDB()
        detect = detector(repeated_action_threshold=2)
        classification = detect.analyze_many(
            [
                soc_event("executor-1", "task-001", "execution_step", {"action": "retry compile", "success": True}),
                soc_event("executor-1", "task-001", "execution_step", {"action": "retry compile", "success": True}),
            ]
        )[-1]
        incident = db.record_incident(classification)
        db.mark_true_positive(incident.incident_id, notes="runaway loop confirmed")
        baseline = BehaviorBaseline.default()

        result = db.refine_detection_baseline(baseline)

        self.assertLess(result.baseline.repeated_action_threshold, baseline.repeated_action_threshold)
        self.assertEqual(result.true_positive_count, 1)

    def test_incident_memory_facade_marks_verdicts(self) -> None:
        memory = IncidentMemorySystem()
        classification = detector().analyze(soc_event("executor-1", "task-001", "network_request", {"url": "https://unknown.test", "decision": "allow"}))

        incident = memory.store_incident(classification)
        false_positive = memory.mark_false_positive(incident.incident_id, notes="domain later allowlisted")
        true_positive = memory.mark_true_positive(incident.incident_id, notes="confirmed exfil attempt")

        self.assertEqual(false_positive.verdict, IncidentVerdict.FALSE_POSITIVE)
        self.assertEqual(true_positive.verdict, IncidentVerdict.TRUE_POSITIVE)
        self.assertEqual(memory.incidents()[0].notes, "confirmed exfil attempt")


if __name__ == "__main__":
    unittest.main()
