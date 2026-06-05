from __future__ import annotations

import inspect

from core.agents import (
    AgentFramework,
    AnalystAgent,
    CriticAgent,
    ExecutorAgent,
    PlannerAgent,
    build_default_agent_registry,
)
from core.agents import analyst_agent, base_agent, critic_agent, executor_agent, planner_agent


def test_default_registry_exposes_requested_agents() -> None:
    registry = build_default_agent_registry()

    descriptors = registry.descriptors()

    assert [descriptor["role"] for descriptor in descriptors] == [
        "analyst",
        "critic",
        "executor",
        "planner",
    ]
    assert registry.select(role="planner").name == "planner_agent"
    assert registry.select(capability="analysis.interpret").name == "analyst_agent"


def test_planner_agent_returns_structured_task_graph() -> None:
    result = PlannerAgent().run({"objective": "Investigate anomalous login"})

    assert result["ok"] is True
    assert result["agent"] == "planner_agent"
    assert result["role"] == "planner"
    assert result["output"]["intent"]["kind"] == "investigate_alert"
    assert result["output"]["ordered_execution_plan"]["task_ids"] == [
        "collect_context",
        "analyze_evidence",
        "recommend_response",
    ]


def test_analyst_agent_interprets_only_supplied_observations() -> None:
    result = AnalystAgent().run(
        {
            "objective": "Review authentication events",
            "observations": [
                {"id": "obs_1", "text": "login failure spike", "severity": "medium"},
                {"id": "obs_2", "text": "normal service heartbeat", "severity": "low"},
            ],
        }
    )

    assert result["ok"] is True
    assert result["output"]["finding"] == "suspicious_patterns_detected"
    assert result["output"]["evidence_ids"] == ["obs_1"]


def test_executor_agent_only_creates_sandbox_request() -> None:
    result = ExecutorAgent().run(
        {
            "task": {
                "task_id": "collect_context",
                "kind": "memory.recall",
                "objective": "Collect context",
                "required_capabilities": ["memory.read"],
            }
        }
    )

    assert result["ok"] is True
    request = result["output"]["sandbox_request"]
    assert result["output"]["decision"] == "sandbox_required"
    assert request["filesystem"] == "sandbox_only"
    assert request["network"] == "disabled"


def test_critic_agent_flags_empty_or_untraceable_subject() -> None:
    result = CriticAgent().run({"subject": {"ok": True, "output": {}}})

    assert result["ok"] is True
    assert result["output"]["decision"] == "revise"
    assert [issue["code"] for issue in result["output"]["issues"]] == [
        "missing_trace",
        "empty_output",
    ]


def test_agents_return_structured_errors_instead_of_raising() -> None:
    result = PlannerAgent().run({"objective": "   "})

    assert result["ok"] is False
    assert result["error"]["type"] == "AgentInputError"
    assert result["error"]["recoverable"] is True


def test_agent_framework_runs_full_structured_pipeline() -> None:
    result = AgentFramework().run_pipeline(
        "Investigate sandbox denial",
        observations=["sandbox deny event observed"],
    )

    assert result["ok"] is True
    assert set(result["results"]) == {"planner", "analyst", "executor", "critic"}
    assert result["results"]["critic"]["output"]["decision"] == "accept"


def test_agent_instances_are_stateless_workers() -> None:
    first = PlannerAgent()
    second = PlannerAgent()

    assert first.descriptor == second.descriptor
    assert first.run({"objective": "Investigate A"})["output"]["ordered_execution_plan"][
        "task_ids"
    ] == second.run({"objective": "Investigate A"})["output"]["ordered_execution_plan"][
        "task_ids"
    ]


def test_core_agents_do_not_import_direct_system_access_modules() -> None:
    sources = "\n".join(
        inspect.getsource(module)
        for module in (
            base_agent,
            planner_agent,
            analyst_agent,
            executor_agent,
            critic_agent,
        )
    )

    forbidden = ("import os", "import subprocess", "from pathlib", "socket", "shutil")
    for token in forbidden:
        assert token not in sources
