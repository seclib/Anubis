"""Mandatory sandbox execution boundary for ANUBIS tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.agents import AgentRegistry, build_default_agent_registry
from core.security import AuditLogger, KillSwitch, PermissionEngine, PermissionRule, SandboxGuard
from core.security.sandbox_guard import FilesystemMode, NetworkMode, SandboxDecision, SandboxRequest


def _default_guard() -> SandboxGuard:
    return SandboxGuard(
        permission_engine=PermissionEngine(
            rules=(
                PermissionRule(
                    actor="executor_agent",
                    actions=frozenset({"sandbox.execute"}),
                    resources=frozenset({"graph_task"}),
                    permissions=frozenset({"sandbox.execute"}),
                    reason="Executor agent may submit sandbox-only graph tasks.",
                ),
            )
        ),
        audit_logger=AuditLogger(),
        kill_switch=KillSwitch(),
    )


@dataclass(frozen=True, slots=True)
class SandboxRunRequest:
    task: Mapping[str, Any]
    run_id: str
    actor: str = "executor_agent"
    resource: str = "graph_task"
    filesystem: FilesystemMode = FilesystemMode.SANDBOX_ONLY
    network: NetworkMode = NetworkMode.DISABLED

    def __post_init__(self) -> None:
        task = dict(self.task)
        for key in ("task_id", "kind", "objective"):
            if not str(task.get(key) or "").strip():
                raise ValueError(f"sandbox task missing required field: {key}")
        object.__setattr__(self, "task", task)
        object.__setattr__(self, "run_id", self.run_id.strip())
        object.__setattr__(self, "actor", self.actor.strip())
        object.__setattr__(self, "resource", self.resource.strip())


@dataclass(frozen=True, slots=True)
class SandboxRunResult:
    task_id: str
    actor: str
    status: str
    executor_result: Mapping[str, Any]
    sandbox_decision: SandboxDecision
    explanation: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.actor,
            "status": self.status,
            "executor_result": dict(self.executor_result),
            "sandbox_decision": self.sandbox_decision.to_dict(),
            "explanation": self.explanation,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class SandboxRunner:
    """Runs all execution requests through one audited sandbox path."""

    registry: AgentRegistry = field(default_factory=build_default_agent_registry)
    guard: SandboxGuard = field(default_factory=_default_guard)

    def run_task(self, request: SandboxRunRequest) -> SandboxRunResult:
        executor = self.registry.select(role="executor")
        if executor.name != request.actor:
            raise ValueError("sandbox actor must match selected executor agent")

        executor_result = executor.run({"task": dict(request.task)})
        decision = self.guard.validate(
            SandboxRequest(
                actor=request.actor,
                action="sandbox.execute",
                resource=request.resource,
                operation=str(request.task["kind"]),
                required_permissions=frozenset(),
                filesystem=request.filesystem,
                network=request.network,
                metadata={
                    "task_id": request.task["task_id"],
                    "run_id": request.run_id,
                    "required_capabilities": tuple(request.task.get("required_capabilities", ())),
                },
            )
        )
        ok = bool(executor_result.get("ok")) and decision.allowed
        return SandboxRunResult(
            task_id=str(request.task["task_id"]),
            actor=request.actor,
            status="succeeded" if ok else "failed",
            executor_result=executor_result,
            sandbox_decision=decision,
            explanation=(
                "Task remained inside the sandbox boundary; no direct system access occurred."
                if ok
                else decision.reason
            ),
            metadata={"runner": "SandboxRunner", "direct_execution": False},
        )


__all__ = ["SandboxRunRequest", "SandboxRunResult", "SandboxRunner"]
