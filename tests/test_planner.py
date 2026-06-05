from __future__ import annotations

from dataclasses import replace

from anubis import (
    AgentDescriptor,
    AgentRunResult,
    Goal,
    Orchestrator,
    PlanStatus,
    PlanningEngine,
    StepStatus,
    TaskResult,
    TaskStatus,
    default_security_templates,
)


async def test_decomposes_goal_and_assigns_agents_deterministically() -> None:
    planner = PlanningEngine(templates=default_security_templates())
    plan = await planner.create_plan(
        Goal(kind="investigate_alert", objective="triage suspicious login"),
        agents=(
            AgentDescriptor("wide", frozenset({"telemetry.read", "reason.plan"})),
            AgentDescriptor("collector", frozenset({"telemetry.read"})),
            AgentDescriptor("reasoner", frozenset({"reason.plan"})),
            AgentDescriptor("policy", frozenset({"policy.evaluate"})),
        ),
    )

    assert plan.status == PlanStatus.RUNNING
    assert [step.id for step in plan.steps] == [
        "collect_context",
        "analyze_evidence",
        "recommend_response",
    ]
    assert plan.step("collect_context").assigned_agent == "collector"
    assert plan.step("analyze_evidence").assigned_agent == "reasoner"
    assert plan.step("recommend_response").assigned_agent == "policy"
    assert plan.step("collect_context").status == StepStatus.READY
    assert plan.step("analyze_evidence").status == StepStatus.PENDING


async def test_re_evaluates_after_success_and_unblocks_next_step() -> None:
    planner = PlanningEngine(templates=default_security_templates())
    plan = await planner.create_plan(
        Goal(kind="investigate_alert", objective="triage suspicious login"),
        agents=(
            AgentDescriptor("collector", frozenset({"telemetry.read"})),
            AgentDescriptor("reasoner", frozenset({"reason.plan"})),
            AgentDescriptor("policy", frozenset({"policy.evaluate"})),
        ),
    )
    dispatched = list(plan.steps)
    dispatched[0] = replace(
        dispatched[0],
        status=StepStatus.DISPATCHED,
        task_id="task_1",
        attempts=1,
    )
    plan = replace(plan, steps=tuple(dispatched))

    plan = planner.apply_result(plan, TaskResult(task_id="task_1", status=TaskStatus.SUCCEEDED))

    assert plan.step("collect_context").status == StepStatus.SUCCEEDED
    assert plan.step("analyze_evidence").status == StepStatus.READY


async def test_failure_with_retry_budget_becomes_ready_again() -> None:
    planner = PlanningEngine(templates=default_security_templates())
    plan = await planner.create_plan(
        Goal(kind="investigate_alert", objective="triage suspicious login"),
        agents=(AgentDescriptor("collector", frozenset({"telemetry.read"})),),
    )
    step = plan.step("collect_context")
    steps = (
        replace(
            step,
            status=StepStatus.DISPATCHED,
            task_id="task_1",
            attempts=1,
        ),
        *plan.steps[1:],
    )
    plan = replace(plan, steps=steps)

    plan = planner.apply_result(
        plan,
        TaskResult(task_id="task_1", status=TaskStatus.FAILED, error="temporary failure"),
    )

    assert plan.step("collect_context").status == StepStatus.READY
    assert plan.step("collect_context").attempts == 1
    assert plan.step("collect_context").last_error == "temporary failure"


async def test_explain_returns_stable_human_readable_trace() -> None:
    planner = PlanningEngine(templates=default_security_templates())
    plan = await planner.create_plan(
        Goal(kind="investigate_alert", objective="triage suspicious login"),
        agents=(AgentDescriptor("collector", frozenset({"telemetry.read"})),),
    )

    explanation = planner.explain(plan)

    assert explanation[0].startswith("Plan ")
    assert "Selected template 'investigate_alert'" in explanation[1]
    assert "collect_context" in explanation[3]
    assert "agent=collector" in explanation[3]


async def test_dispatch_ready_submits_bound_agent_assignment() -> None:
    orchestrator = Orchestrator()
    calls: list[str] = []

    async def wide_handler(_: object) -> AgentRunResult:
        calls.append("wide")
        return AgentRunResult()

    async def exact_handler(_: object) -> AgentRunResult:
        calls.append("exact")
        return AgentRunResult()

    await orchestrator.register_agent(
        AgentDescriptor("wide", frozenset({"telemetry.read", "reason.plan"})),
        wide_handler,
    )
    await orchestrator.register_agent(
        AgentDescriptor("exact", frozenset({"telemetry.read"})),
        exact_handler,
    )

    planner = PlanningEngine(
        templates=default_security_templates(),
        agent_registry=orchestrator.agent_registry,
    )
    plan = await planner.create_plan(
        Goal(kind="investigate_alert", objective="triage suspicious login"),
    )

    plan = await planner.dispatch_ready(plan, orchestrator)
    result = await orchestrator.wait(plan.step("collect_context").task_id or "")

    assert result.status == TaskStatus.SUCCEEDED
    assert calls == ["exact"]
