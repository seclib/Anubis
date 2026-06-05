from __future__ import annotations

import inspect

import core.planner.planner as planner_module
from core.planner import (
    DependencyResolutionError,
    DependencyResolver,
    InputIntent,
    PlanningEngine,
    PlanValidationError,
    TaskGraph,
    TaskNode,
)


def test_planner_converts_input_to_graph_and_ordered_plan() -> None:
    engine = PlanningEngine()

    graph = engine.create_task_graph("Investigate suspicious login from payroll host")
    plan = engine.plan("Investigate suspicious login from payroll host")

    assert graph.intent.kind == "investigate_alert"
    assert graph.intent.objective == "Investigate suspicious login from payroll host"
    assert graph.task_ids == ("collect_context", "analyze_evidence", "recommend_response")
    assert plan.task_ids == ("collect_context", "analyze_evidence", "recommend_response")
    assert plan.ordered_tasks[0].required_capabilities == frozenset(
        {"memory.read", "telemetry.read"}
    )
    assert "dependencies first" in plan.explanation[1]


def test_unknown_intent_kind_uses_deterministic_general_rule() -> None:
    engine = PlanningEngine()

    plan = engine.plan("Summarize latest internal notes", intent_kind="unknown_kind")

    assert plan.graph.intent.kind == "general_task"
    assert plan.task_ids == ("clarify_objective", "structure_response")


def test_dependency_resolver_orders_ready_tasks_by_priority_then_id() -> None:
    intent = InputIntent(kind="general_task", objective="order independent tasks")
    graph = TaskGraph(
        graph_id="graph_ordering",
        intent=intent,
        nodes=(
            TaskNode(task_id="z_second", kind="analysis", objective="second", priority=20),
            TaskNode(task_id="b_first", kind="analysis", objective="first b", priority=10),
            TaskNode(task_id="a_first", kind="analysis", objective="first a", priority=10),
        ),
    )

    plan = DependencyResolver().resolve(graph)

    assert plan.task_ids == ("a_first", "b_first", "z_second")


def test_dependency_resolver_rejects_unknown_dependencies() -> None:
    intent = InputIntent(kind="general_task", objective="bad dependency")
    graph = TaskGraph(
        graph_id="graph_missing_dependency",
        intent=intent,
        nodes=(
            TaskNode(
                task_id="analyze",
                kind="analysis",
                objective="analyze",
                depends_on=frozenset({"missing"}),
            ),
        ),
    )

    try:
        DependencyResolver().resolve(graph)
    except PlanValidationError as exc:
        assert "unknown dependencies" in str(exc)
    else:
        raise AssertionError("expected PlanValidationError")


def test_dependency_resolver_rejects_cycles() -> None:
    intent = InputIntent(kind="general_task", objective="cyclic plan")
    graph = TaskGraph(
        graph_id="graph_cycle",
        intent=intent,
        nodes=(
            TaskNode(
                task_id="first",
                kind="analysis",
                objective="first",
                depends_on=frozenset({"second"}),
            ),
            TaskNode(
                task_id="second",
                kind="analysis",
                objective="second",
                depends_on=frozenset({"first"}),
            ),
        ),
    )

    try:
        DependencyResolver().resolve(graph)
    except DependencyResolutionError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("expected DependencyResolutionError")


def test_planner_module_contains_no_execution_or_dispatch_logic() -> None:
    engine = PlanningEngine()
    source = inspect.getsource(planner_module)

    assert not hasattr(engine, "dispatch_ready")
    assert "Orchestrator" not in source
    assert ".execute(" not in source
    assert ".dispatch(" not in source
