from __future__ import annotations

from core.graph import GRAPH_NODE_ORDER, GraphOrchestrator, graph_architecture_design


def test_graph_architecture_declares_required_nodes() -> None:
    design = graph_architecture_design()

    assert design["style"] == "LangGraph-inspired deterministic state graph"
    assert tuple(node["name"] for node in design["nodes"]) == GRAPH_NODE_ORDER
    assert design["rules"]["self_modification"] == "forbidden"


def test_graph_orchestrator_runs_full_state_path() -> None:
    orchestrator = GraphOrchestrator.build()
    result = orchestrator.run_once("Investigate sandbox anomaly", source="test")
    payload = result.to_dict()

    assert result.succeeded
    assert payload["goal"] == "Investigate sandbox anomaly"
    assert payload["execution_path"] == GRAPH_NODE_ORDER
    assert payload["task_ids"] == ("collect_context", "analyze_evidence", "recommend_response")
    assert payload["memory"]["episode_id"].startswith("episode_")
    assert payload["reflection"]["success_rate"] == 1.0
    assert len(payload["state_history"]) == 10
    assert payload["state_transitions"][-1]["action"] == "state.graph.succeeded"
    assert not payload["errors"]


def test_graph_orchestrator_returns_structured_error_for_empty_input() -> None:
    orchestrator = GraphOrchestrator.build()
    result = orchestrator.run_once("   ", source="test")
    payload = result.to_dict()

    assert not result.succeeded
    assert payload["status"] == "failed"
    assert payload["errors"][0]["node"] == "input"
