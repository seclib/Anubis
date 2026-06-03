import unittest

from anubis.distributed import (
    AgentRegistration,
    AgentRegistry,
    AgentType,
    AnomalyDetectionEngine,
    BehaviorBaseline,
    BehaviorScoringSystem,
    CentralSOCEventCollector,
    KillSwitchController,
    RiskClassifier,
    SOCEventType,
    SOCDashboardAPI,
    SOCMetricsAggregator,
    SOCResponseEngine,
)


class SOCDashboardBackendTest(unittest.TestCase):
    def build_stack(self):
        collector = CentralSOCEventCollector()
        kill_switch = KillSwitchController()
        response = SOCResponseEngine(kill_switch=kill_switch)
        registry = AgentRegistry()
        registry.register(AgentRegistration(agent_id="planner-1", agent_type=AgentType.PLANNER))
        registry.register(AgentRegistration(agent_id="executor-1", agent_type=AgentType.EXECUTOR))
        aggregator = SOCMetricsAggregator(
            collector=collector,
            response_engine=response,
            kill_switch=kill_switch,
            agent_registry=registry,
        )
        api = SOCDashboardAPI(aggregator)
        detector = AnomalyDetectionEngine(RiskClassifier(BehaviorScoringSystem(BehaviorBaseline.default())))
        return collector, response, aggregator, api, detector

    def ingest_and_classify(self, collector, aggregator, detector, raw, *, agent_id, task_id, event_type):
        event = collector.ingest(raw, agent_id=agent_id, task_id=task_id, event_type=event_type)
        aggregator.record_event(event)
        classification = detector.analyze(event)
        aggregator.record_classification(classification)
        return event, classification

    def test_status_reports_security_state_and_kill_switch(self) -> None:
        collector, response, aggregator, api, detector = self.build_stack()
        _event, classification = self.ingest_and_classify(
            collector,
            aggregator,
            detector,
            {"payload": {"requested_path": "/etc/passwd", "decision": "deny", "action": "read"}},
            agent_id="executor-1",
            task_id="task-001",
            event_type=SOCEventType.FILE_ACCESS,
        )
        result = response.respond(classification)
        aggregator.record_response(result)

        status = api.status()

        self.assertEqual(status["active_agents"], 2)
        self.assertEqual(status["active_threats"], 1)
        self.assertGreaterEqual(status["blocked_actions"], 2)
        self.assertEqual(status["total_events"], 1)
        self.assertEqual(status["max_risk_score"], 3)
        self.assertEqual(status["kill_switch_status"]["state"], "recovery")

    def test_threats_endpoint_returns_active_findings(self) -> None:
        collector, _response, aggregator, api, detector = self.build_stack()
        self.ingest_and_classify(
            collector,
            aggregator,
            detector,
            {"payload": {"url": "https://unknown.test/api", "decision": "allow"}},
            agent_id="executor-1",
            task_id="task-001",
            event_type=SOCEventType.NETWORK_REQUEST,
        )

        status, payload = api.handle("/threats")

        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(payload["threats"]), 1)
        self.assertEqual(payload["threats"][0]["agent_id"], "executor-1")
        self.assertIn(payload["threats"][0]["code"], {"role_violation", "unexpected_external_call"})

    def test_agents_endpoint_reports_risk_per_agent_and_blocked_actions(self) -> None:
        collector, response, aggregator, api, detector = self.build_stack()
        _event, classification = self.ingest_and_classify(
            collector,
            aggregator,
            detector,
            {"payload": {"message": "boom"}},
            agent_id="executor-1",
            task_id="task-001",
            event_type=SOCEventType.SYSTEM_ERROR,
        )
        result = response.respond(classification)
        aggregator.record_response(result)

        _status, payload = api.handle("/agents")
        agents = {agent["agent_id"]: agent for agent in payload["agents"]}

        self.assertTrue(agents["executor-1"]["active"])
        self.assertEqual(agents["executor-1"]["risk_score"], 1)
        self.assertTrue(agents["executor-1"]["throttled"])
        self.assertEqual(agents["executor-1"]["blocked_action_count"], 1)
        self.assertTrue(agents["planner-1"]["active"])

    def test_events_endpoint_supports_limit(self) -> None:
        collector, _response, aggregator, api, detector = self.build_stack()
        for index in range(3):
            self.ingest_and_classify(
                collector,
                aggregator,
                detector,
                {"payload": {"index": index}},
                agent_id="executor-1",
                task_id=f"task-{index}",
                event_type=SOCEventType.AGENT_ACTION,
            )

        status, payload = api.handle("/events", query={"limit": 2})

        self.assertEqual(status, 200)
        self.assertEqual(len(payload["events"]), 2)
        self.assertEqual(payload["events"][0]["task_id"], "task-1")
        self.assertEqual(payload["events"][1]["task_id"], "task-2")

    def test_live_feed_streams_events_alerts_and_responses(self) -> None:
        collector, response, aggregator, api, detector = self.build_stack()
        received = []
        api.subscribe_live_feed(received.append)

        _event, classification = self.ingest_and_classify(
            collector,
            aggregator,
            detector,
            {"payload": {"message": "boom"}},
            agent_id="executor-1",
            task_id="task-001",
            event_type=SOCEventType.SYSTEM_ERROR,
        )
        aggregator.record_response(response.respond(classification))

        self.assertEqual([item["kind"] for item in received], ["event", "alert", "response"])
        self.assertEqual(len(api.live_feed()), 3)

    def test_unknown_route_returns_404(self) -> None:
        _collector, _response, _aggregator, api, _detector = self.build_stack()

        status, payload = api.handle("/missing")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not found")


if __name__ == "__main__":
    unittest.main()
