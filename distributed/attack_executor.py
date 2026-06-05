"""Sandboxed execution harness for simulated ANUBIS red team attacks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any

from anubis.distributed.attack_generator import AttackScenario, AttackType
from anubis.distributed.dag_builder import DAGBuilder, TaskGraphError
from anubis.distributed.permission_manager import PermissionManager, ToolExecutionContext
from anubis.distributed.sandbox_runtime import SandboxContext, SandboxRuntime, SandboxViolation
from anubis.distributed.task_graph import TaskGraph, TaskGraphNode, TaskGraphNodeType


class AttackExecutionStatus(StrEnum):
    CONTAINED = "contained"
    BYPASS_DETECTED = "bypass_detected"
    INVALID = "invalid"


@dataclass(frozen=True)
class AttackExecutionLogEntry:
    attack_id: str
    message: str
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "message": self.message,
            "success": self.success,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }


class AttackExecutionLogger:
    """Records every simulated attack execution observation and failure."""

    def __init__(self) -> None:
        self._entries: list[AttackExecutionLogEntry] = []
        self._lock = RLock()

    def record(self, entry: AttackExecutionLogEntry) -> AttackExecutionLogEntry:
        with self._lock:
            self._entries.append(entry)
        return entry

    def entries(self) -> tuple[AttackExecutionLogEntry, ...]:
        with self._lock:
            return tuple(self._entries)


@dataclass(frozen=True)
class AttackExecutionResult:
    attack_id: str
    attack_type: str
    target: str
    status: AttackExecutionStatus
    success: bool
    sandbox_id: str
    system_response: dict[str, Any] = field(default_factory=dict)
    bypass_detected: bool = False
    logs: tuple[AttackExecutionLogEntry, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "attack_type": self.attack_type,
            "target": self.target,
            "status": self.status.value,
            "success": self.success,
            "sandbox_id": self.sandbox_id,
            "system_response": dict(self.system_response),
            "bypass_detected": self.bypass_detected,
            "logs": [entry.to_dict() for entry in self.logs],
            "error": self.error,
        }


class SandboxAttackRunner:
    """Runs simulated attacks inside an ANUBIS sandbox context."""

    def __init__(
        self,
        *,
        runtime: SandboxRuntime | None = None,
        permission_manager: PermissionManager | None = None,
        dag_builder: DAGBuilder | None = None,
        logger: AttackExecutionLogger | None = None,
        event_flood_threshold: int = 1000,
    ) -> None:
        self.runtime = runtime or SandboxRuntime()
        self.permission_manager = permission_manager or PermissionManager()
        self.dag_builder = dag_builder or DAGBuilder()
        self.logger = logger or AttackExecutionLogger()
        self.event_flood_threshold = event_flood_threshold

    def run(self, scenario: AttackScenario, *, context: SandboxContext | None = None) -> AttackExecutionResult:
        context = context or self.runtime.create(str(scenario.payload.get("task_id") or scenario.attack_id))
        start_index = len(self.logger.entries())
        try:
            self._validate_simulation_contract(scenario, context)
            response = self._execute_simulation(scenario, context)
            bypass = not bool(response.get("contained", False))
            status = AttackExecutionStatus.BYPASS_DETECTED if bypass else AttackExecutionStatus.CONTAINED
            self._log(scenario, "simulated attack execution completed", not bypass, response)
            logs = self.logger.entries()[start_index:]
            return AttackExecutionResult(
                attack_id=scenario.attack_id,
                attack_type=scenario.type.value,
                target=scenario.target.value,
                status=status,
                success=not bypass,
                sandbox_id=context.sandbox_id,
                system_response=response,
                bypass_detected=bypass,
                logs=logs,
            )
        except Exception as exc:
            self._log(scenario, "simulated attack execution failed", False, {"error": str(exc), "error_type": type(exc).__name__})
            logs = self.logger.entries()[start_index:]
            return AttackExecutionResult(
                attack_id=scenario.attack_id,
                attack_type=scenario.type.value,
                target=scenario.target.value,
                status=AttackExecutionStatus.INVALID,
                success=False,
                sandbox_id=context.sandbox_id,
                system_response={"contained": True, "error_type": type(exc).__name__},
                bypass_detected=False,
                logs=logs,
                error=str(exc),
            )

    def _validate_simulation_contract(self, scenario: AttackScenario, context: SandboxContext) -> None:
        payload = scenario.payload
        sandbox = payload.get("sandbox")
        if payload.get("simulation_only") is not True:
            raise ValueError("attack scenario must be simulation_only")
        if not isinstance(sandbox, dict) or sandbox.get("required") is not True:
            raise ValueError("attack scenario must require sandbox execution")
        if sandbox.get("host_filesystem_access") is not False or sandbox.get("host_mutation_allowed") is not False:
            raise ValueError("attack scenario must explicitly deny host access and mutation")
        expected = sandbox.get("sandbox_id")
        if expected and expected != context.sandbox_id and not str(context.sandbox_id).startswith(str(expected).rstrip("-")):
            self._log(scenario, "sandbox id differs from scenario hint", True, {"expected": expected, "actual": context.sandbox_id})

    def _execute_simulation(self, scenario: AttackScenario, context: SandboxContext) -> dict[str, Any]:
        if scenario.type == AttackType.TOOL_ABUSE:
            return self._simulate_tool_abuse(scenario)
        if scenario.type == AttackType.FILESYSTEM:
            return self._simulate_filesystem_attack(scenario, context)
        if scenario.type == AttackType.EVENT_FLOODING:
            return self._simulate_event_flooding(scenario)
        if scenario.type == AttackType.LOGIC_CORRUPTION:
            return self._simulate_logic_corruption(scenario)
        raise ValueError(f"unsupported attack type: {scenario.type}")

    def _simulate_tool_abuse(self, scenario: AttackScenario) -> dict[str, Any]:
        payload = scenario.payload
        denied: list[dict[str, Any]] = []
        approved: list[dict[str, Any]] = []
        for tool in payload.get("requested_tools", ()):
            decision = self.permission_manager.check(
                str(tool),
                ToolExecutionContext(agent_type="executor", task_id=str(payload.get("task_id")), sandboxed=True),
            )
            (approved if decision.approved else denied).append(decision.to_dict())

        attempted_action = payload.get("attempted_action")
        role_violation = attempted_action in {"plan_dependencies", "decompose_task", "create_plan"}
        contained = bool(denied) or role_violation
        return {
            "contained": contained,
            "execution_type": "permission_bypass_attempt" if denied else "malformed_role_action",
            "denied_permissions": denied,
            "approved_permissions": approved,
            "role_violation_detected": role_violation,
            "real_tools_executed": False,
            "network_calls_made": False,
        }

    def _simulate_filesystem_attack(self, scenario: AttackScenario, context: SandboxContext) -> dict[str, Any]:
        path = str(scenario.payload.get("path", ""))
        try:
            resolved = self.runtime.resolve_path(context, path)
            contained = False
            reason = "path unexpectedly resolved"
            resolved_path = str(resolved)
        except SandboxViolation as exc:
            contained = True
            reason = str(exc)
            resolved_path = None
        return {
            "contained": contained,
            "execution_type": "permission_bypass_attempt",
            "path": path,
            "resolved_path": resolved_path,
            "reason": reason,
            "host_write_performed": False,
            "host_read_performed": False,
            "network_calls_made": False,
        }

    def _simulate_event_flooding(self, scenario: AttackScenario) -> dict[str, Any]:
        count = int(scenario.payload.get("simulated_count") or 0)
        return {
            "contained": count >= self.event_flood_threshold,
            "execution_type": "task_injection" if scenario.payload.get("event_type") == "task_created" else "resource_exhaustion_simulation",
            "simulated_count": count,
            "threshold": self.event_flood_threshold,
            "real_events_enqueued": 0,
            "queue_overload_simulated": True,
            "backpressure_expected": count >= self.event_flood_threshold,
            "network_calls_made": False,
        }

    def _simulate_logic_corruption(self, scenario: AttackScenario) -> dict[str, Any]:
        graph = _graph_from_payload(scenario.payload)
        try:
            self.dag_builder.validate(graph)
            return {
                "contained": False,
                "execution_type": "malformed_input",
                "dag_valid": True,
                "reason": "malformed DAG was accepted",
                "network_calls_made": False,
            }
        except TaskGraphError as exc:
            return {
                "contained": True,
                "execution_type": "malformed_input",
                "dag_valid": False,
                "reason": str(exc),
                "network_calls_made": False,
            }

    def _log(self, scenario: AttackScenario, message: str, success: bool, metadata: dict[str, Any] | None = None) -> AttackExecutionLogEntry:
        return self.logger.record(
            AttackExecutionLogEntry(
                attack_id=scenario.attack_id,
                message=message,
                success=success,
                metadata=dict(metadata or {}),
            )
        )


class AttackExecutor:
    """Facade for executing red-team scenario batches in sandboxed simulation mode."""

    def __init__(self, runner: SandboxAttackRunner | None = None) -> None:
        self.runner = runner or SandboxAttackRunner()

    def execute(self, scenario: AttackScenario, *, context: SandboxContext | None = None) -> AttackExecutionResult:
        return self.runner.run(scenario, context=context)

    def execute_many(self, scenarios: tuple[AttackScenario, ...] | list[AttackScenario]) -> tuple[AttackExecutionResult, ...]:
        return tuple(self.execute(scenario) for scenario in scenarios)


def _graph_from_payload(payload: dict[str, Any]) -> TaskGraph:
    nodes = []
    for raw_node in payload.get("nodes", ()):
        nodes.append(
            TaskGraphNode(
                id=str(raw_node["id"]),
                type=TaskGraphNodeType(str(raw_node["type"])),
                depends_on=tuple(str(dependency) for dependency in raw_node.get("depends_on", ())),
                payload={},
            )
        )
    return TaskGraph(task_id=str(payload.get("task_id") or "red-team-dag"), nodes=tuple(nodes))


__all__ = [
    "AttackExecutionLogEntry",
    "AttackExecutionLogger",
    "AttackExecutionResult",
    "AttackExecutionStatus",
    "AttackExecutor",
    "SandboxAttackRunner",
]
