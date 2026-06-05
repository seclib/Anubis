from __future__ import annotations

from pathlib import Path

from core.agents import AgentDescriptor, BaseAgent
from core.execution import SandboxRunRequest, SandboxRunner
from core.memory import MemorySystem
from core.plugins import BasePlugin, PluginEcosystem, PluginManifest, PluginRequest, PluginType
from core.security import (
    ActionRequest,
    FilesystemMode,
    PermissionRule,
    SecurityKernel,
    SandboxRequest,
)
from core.swarm import SwarmCoordinator


def test_swarm_native_runs_interchangeable_agents() -> None:
    swarm = SwarmCoordinator()

    result = swarm.run("Investigate swarm-native anomaly")
    payload = result.to_dict()

    assert payload["decision"]["accepted"] is True
    assert payload["decision"]["decision"] == "accept"
    assert [item["role"] for item in payload["agent_outputs"]] == [
        "planner",
        "analyst",
        "executor",
        "critic",
    ]


def test_memory_first_system_has_strong_separation() -> None:
    memory = MemorySystem()

    memory.remember_short_term(key="active_goal", value={"goal": "triage"}, actor="test")
    fact = memory.remember_fact(
        subject="anubis",
        predicate="architecture",
        value="memory-first",
        source="test",
    )
    snapshot = memory.snapshot()

    assert snapshot["separation"] == "strong"
    assert snapshot["short_term"]["count"] == 1
    assert snapshot["long_term"]["semantic_count"] == 1
    assert snapshot["semantic_vectors"]["vector_count"] == 1
    assert fact["record_id"].startswith("semantic_")


def test_sandbox_runner_is_mandatory_execution_boundary() -> None:
    runner = SandboxRunner()
    result = runner.run_task(
        SandboxRunRequest(
            run_id="test_run",
            task={
                "task_id": "task_1",
                "kind": "safe.prepare",
                "objective": "prepare only",
                "required_capabilities": [],
            },
        )
    )
    payload = result.to_dict()

    assert payload["status"] == "succeeded"
    assert payload["metadata"]["runner"] == "SandboxRunner"
    assert payload["metadata"]["direct_execution"] is False
    assert payload["sandbox_decision"]["allowed"] is True


def test_security_kernel_centralizes_permissions_threats_and_kill_switch() -> None:
    kernel = SecurityKernel()
    kernel.permission_engine.add_rule(
        PermissionRule(
            actor="agent",
            actions=frozenset({"read"}),
            resources=frozenset({"memory"}),
            permissions=frozenset({"memory.read"}),
        )
    )

    allowed = kernel.authorize(
        ActionRequest(
            actor="agent",
            action="read",
            resource="memory",
            required_permissions=frozenset({"memory.read"}),
        )
    )
    denied = kernel.validate_sandbox(
        SandboxRequest(
            actor="agent",
            action="sandbox.execute",
            resource="graph_task",
            operation="escape_probe",
            filesystem=FilesystemMode.NONE,
        )
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert kernel.kill_switch.active is True
    assert kernel.snapshot()["audit_records"] >= 2


class EchoPlugin(BasePlugin):
    manifest = PluginManifest(
        plugin_id="echo",
        name="Echo",
        version="1.0.0",
        plugin_type=PluginType.TOOL,
        entrypoint="echo",
        permissions=frozenset({"plugin.echo"}),
    )

    def execute(self, request: PluginRequest):
        return {"echo": dict(request.payload)}


def test_plugin_ecosystem_is_sandboxed_and_catalogued() -> None:
    ecosystem = PluginEcosystem()
    ecosystem.manager.permission_engine.add_rule(
        PermissionRule(
            actor="plugin:echo",
            actions=frozenset({"plugin.run"}),
            resources=frozenset({"plugin:echo"}),
            permissions=frozenset({"plugin.echo", "sandbox.execute"}),
        )
    )

    ecosystem.install_instance(EchoPlugin())
    ecosystem.start("echo")
    result = ecosystem.execute(plugin_id="echo", action="run", payload={"value": 3})

    assert result["ok"] is True
    assert result["output"]["echo"] == {"value": 3}
    assert ecosystem.catalog()[0]["manifest"]["plugin_id"] == "echo"


def test_auto_refactor_ci_is_review_only() -> None:
    policy = Path("ci/auto_refactor.yml").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/auto-refactor.yml").read_text(encoding="utf-8")

    assert "proposal_only" in policy
    assert "auto_push: false" in policy
    assert "auto_merge: false" in policy
    assert "auto_deploy: false" in policy
    assert "actions/upload-artifact" in workflow
    assert "git push" not in workflow
