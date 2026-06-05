from __future__ import annotations

from typing import Any, Mapping

from core.graph import (
    ConditionalRoute,
    DeterministicGraphRunner,
    GraphDefinition,
    GraphNode,
    GraphOrchestrator,
    GraphRunStatus,
    GraphState,
    NodeResult,
    RouteCondition,
)


class SetContextNode(GraphNode):
    def __init__(self, name: str, output_key: str, output_value: Any) -> None:
        self.name = name
        self.output_key = output_key
        self.output_value = output_value

    def run(self, state: GraphState) -> NodeResult:
        output = {self.output_key: self.output_value}
        return NodeResult(
            state=state.with_updates(output={**dict(state.output), **output}),
            explanation=f"Set {self.output_key}.",
            outputs=output,
        )


def test_graph_runtime_supports_deterministic_conditional_flow() -> None:
    nodes: Mapping[str, GraphNode] = {
        "start": SetContextNode("start", "started", True),
        "middle": SetContextNode("middle", "middle_seen", True),
        "end": SetContextNode("end", "ended", True),
    }
    runner = DeterministicGraphRunner(
        nodes=nodes,
        definition=GraphDefinition(
            entrypoint="start",
            terminal="end",
            edges={"start": "middle", "middle": "end"},
            conditional_edges={
                "start": (
                    ConditionalRoute(
                        name="skip_middle_when_requested",
                        target="end",
                        condition=RouteCondition("context.skip_middle", equals=True),
                        priority=10,
                    ),
                )
            },
        ),
    )

    final_state = runner.run(
        GraphState(
            run_id="graph_runtime_conditional_001",
            stimulus="test conditional",
            context={"skip_middle": True},
        )
    )
    debug = runner.debug_report("graph_runtime_conditional_001").to_dict()

    assert final_state.status == GraphRunStatus.SUCCEEDED
    assert final_state.execution_path == ("start", "end")
    assert "middle_seen" not in final_state.output
    assert debug["route_decisions"][0]["route_name"] == "skip_middle_when_requested"
    assert debug["route_decisions"][0]["conditional"] is True
    assert any(record["action"] == "edge.selected" for record in debug["log_records"])


def test_graph_runtime_uses_default_edge_when_condition_does_not_match() -> None:
    nodes: Mapping[str, GraphNode] = {
        "start": SetContextNode("start", "started", True),
        "middle": SetContextNode("middle", "middle_seen", True),
        "end": SetContextNode("end", "ended", True),
    }
    runner = DeterministicGraphRunner(
        nodes=nodes,
        definition=GraphDefinition(
            entrypoint="start",
            terminal="end",
            edges={"start": "middle", "middle": "end"},
            conditional_edges={
                "start": (
                    ConditionalRoute(
                        name="skip_middle_when_requested",
                        target="end",
                        condition=RouteCondition("context.skip_middle", equals=True),
                    ),
                )
            },
        ),
    )

    final_state = runner.run(
        GraphState(
            run_id="graph_runtime_default_001",
            stimulus="test default",
            context={"skip_middle": False},
        )
    )
    debug = runner.debug_report("graph_runtime_default_001").to_dict()

    assert final_state.execution_path == ("start", "middle", "end")
    assert final_state.output["middle_seen"] is True
    assert debug["route_decisions"][0]["route_name"] == "default"
    assert debug["route_decisions"][0]["conditional"] is False


def test_graph_orchestrator_debug_report_exposes_path_and_versions() -> None:
    orchestrator = GraphOrchestrator.build()
    result = orchestrator.run_once("Investigate runtime debugging", source="test")
    debug = orchestrator.debug_run(result.state.run_id).to_dict()

    assert debug["status"] == "succeeded"
    assert debug["execution_path"] == result.state.execution_path
    assert len(debug["node_traces"]) == len(result.state.execution_path)
    assert len(debug["state_versions"]) == 10
    assert len(debug["route_decisions"]) == len(result.state.execution_path) - 1
