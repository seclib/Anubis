from __future__ import annotations

import asyncio

from anubis import (
    AgentRunResult,
    CapabilityGrant,
    EventType,
    ExecutionLayer,
    ExecutionStatus,
    FilesystemPolicy,
    InMemoryEventBus,
    IsolationProfile,
    NetworkPolicy,
    PermissionEffect,
    PermissionSet,
    PermissionSystem,
    Sandbox,
    SandboxPolicy,
    SandboxRequest,
    Task,
)


def test_sandbox_denies_missing_permissions_by_default() -> None:
    sandbox = Sandbox()
    task = Task(kind="scan", required_capabilities=frozenset({"network.scan"}))

    decision = sandbox.authorize(
        SandboxRequest(
            task=task,
            agent_name="agent",
            requested_capabilities=task.required_capabilities,
        )
    )

    assert decision.allowed is False
    assert decision.missing_capabilities == ("network.scan",)


def test_permission_system_denies_explicit_deny_even_with_allow() -> None:
    permissions = PermissionSystem(
        (
            PermissionSet(
                agent_name="agent",
                grants=frozenset(
                    {
                        CapabilityGrant("network.scan"),
                        CapabilityGrant("network.scan", PermissionEffect.DENY),
                    }
                ),
            ),
        )
    )
    sandbox = Sandbox(permissions=permissions)
    task = Task(kind="scan", required_capabilities=frozenset({"network.scan"}))

    decision = sandbox.authorize(
        SandboxRequest(
            task=task,
            agent_name="agent",
            requested_capabilities=task.required_capabilities,
        )
    )

    assert decision.allowed is False


def test_sandbox_allows_granted_task_and_selects_profile() -> None:
    profile = IsolationProfile(
        name="network-readonly",
        filesystem=FilesystemPolicy.READ_ONLY,
        network=NetworkPolicy.ALLOWLIST,
        allowed_hosts=("10.0.0.1",),
    )
    sandbox = Sandbox(
        permissions=PermissionSystem(
            (
                PermissionSet(
                    agent_name="agent",
                    grants=frozenset({CapabilityGrant("network.scan")}),
                ),
            )
        ),
        policy=SandboxPolicy(profiles_by_capability={"network.scan": profile}),
    )
    task = Task(kind="scan", required_capabilities=frozenset({"network.scan"}))

    decision = sandbox.authorize(
        SandboxRequest(
            task=task,
            agent_name="agent",
            requested_capabilities=task.required_capabilities,
        )
    )

    assert decision.allowed is True
    assert decision.profile == profile


async def test_execution_layer_blocks_denied_sandbox_task() -> None:
    bus = InMemoryEventBus()
    called = False
    layer = ExecutionLayer(event_bus=bus, sandbox=Sandbox())

    async def executor(_: Task) -> AgentRunResult:
        nonlocal called
        called = True
        return AgentRunResult()

    result = await layer.run(
        task=Task(kind="scan", required_capabilities=frozenset({"network.scan"})),
        agent_name="agent",
        executor=executor,
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.attempts == 0
    assert called is False
    assert EventType.SANDBOX_DENIED in [event.type for event in bus.events]


async def test_execution_layer_runs_allowed_sandbox_task() -> None:
    bus = InMemoryEventBus()
    layer = ExecutionLayer(
        event_bus=bus,
        sandbox=Sandbox(
            permissions=PermissionSystem(
                (
                    PermissionSet(
                        agent_name="agent",
                        grants=frozenset({CapabilityGrant("telemetry.read")}),
                    ),
                )
            )
        ),
    )

    async def executor(_: Task) -> AgentRunResult:
        return AgentRunResult({"ok": True})

    result = await layer.run(
        task=Task(kind="read", required_capabilities=frozenset({"telemetry.read"})),
        agent_name="agent",
        executor=executor,
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.result is not None
    assert result.result.output["ok"] is True
    assert EventType.SANDBOX_ALLOWED in [event.type for event in bus.events]

