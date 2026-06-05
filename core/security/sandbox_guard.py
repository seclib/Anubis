"""Sandbox guard for validating all execution requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from core.security.audit_logger import AuditLogger
from core.security.kill_switch import KillSwitch
from core.security.permission_engine import ActionRequest, PermissionDecision, PermissionEngine


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class FilesystemMode(StrEnum):
    NONE = "none"
    SANDBOX_ONLY = "sandbox_only"


class NetworkMode(StrEnum):
    DISABLED = "disabled"
    EXPLICIT = "explicit"


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    actor: str
    action: str
    resource: str
    operation: str
    required_permissions: frozenset[str] = field(default_factory=frozenset)
    filesystem: FilesystemMode = FilesystemMode.SANDBOX_ONLY
    network: NetworkMode = NetworkMode.DISABLED
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise ValueError("actor cannot be empty")
        if not self.action.strip():
            raise ValueError("action cannot be empty")
        if not self.resource.strip():
            raise ValueError("resource cannot be empty")
        if not self.operation.strip():
            raise ValueError("operation cannot be empty")
        object.__setattr__(self, "actor", self.actor.strip())
        object.__setattr__(self, "action", self.action.strip())
        object.__setattr__(self, "resource", self.resource.strip())
        object.__setattr__(self, "operation", self.operation.strip())
        object.__setattr__(
            self,
            "required_permissions",
            frozenset(sorted(item.strip() for item in self.required_permissions if item.strip())),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_action_request(self) -> ActionRequest:
        permissions = set(self.required_permissions)
        permissions.add("sandbox.execute")
        if self.network == NetworkMode.EXPLICIT:
            permissions.add("network.explicit")
        return ActionRequest(
            actor=self.actor,
            action=self.action,
            resource=self.resource,
            required_permissions=frozenset(permissions),
            context={
                "operation": self.operation,
                "filesystem": self.filesystem,
                "network": self.network,
                **dict(self.metadata),
            },
        )


@dataclass(frozen=True, slots=True)
class SandboxDecision:
    allowed: bool
    request: SandboxRequest
    reason: str
    permission_decision: PermissionDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "request": {
                "actor": self.request.actor,
                "action": self.request.action,
                "resource": self.request.resource,
                "operation": self.request.operation,
                "required_permissions": sorted(self.request.required_permissions),
                "filesystem": self.request.filesystem,
                "network": self.request.network,
                "metadata": dict(self.request.metadata),
            },
            "reason": self.reason,
            "permission_decision": (
                None if self.permission_decision is None else self.permission_decision.to_dict()
            ),
        }


class SandboxGuard:
    """Validates sandbox execution requests through one mandatory path."""

    def __init__(
        self,
        *,
        permission_engine: PermissionEngine,
        audit_logger: AuditLogger,
        kill_switch: KillSwitch,
    ) -> None:
        self.permission_engine = permission_engine
        self.audit_logger = audit_logger
        self.kill_switch = kill_switch

    def validate(self, request: SandboxRequest) -> SandboxDecision:
        kill_decision = self.kill_switch.validate_action(request.action)
        if not kill_decision.allowed:
            decision = SandboxDecision(
                allowed=False,
                request=request,
                reason=kill_decision.reason,
            )
            self._audit(decision)
            return decision

        invariant_failure = self._validate_invariants(request)
        if invariant_failure is not None:
            decision = SandboxDecision(
                allowed=False,
                request=request,
                reason=invariant_failure,
            )
            self._audit(decision)
            return decision

        permission_decision = self.permission_engine.validate(request.to_action_request())
        decision = SandboxDecision(
            allowed=permission_decision.allowed,
            request=request,
            reason=permission_decision.reason,
            permission_decision=permission_decision,
        )
        self._audit(decision)
        return decision

    @staticmethod
    def _validate_invariants(request: SandboxRequest) -> str | None:
        if request.filesystem != FilesystemMode.SANDBOX_ONLY:
            return "Sandbox denied: filesystem must be sandbox_only."
        if request.network not in {NetworkMode.DISABLED, NetworkMode.EXPLICIT}:
            return "Sandbox denied: unsupported network mode."
        if "source.modify" in request.required_permissions:
            return "Sandbox denied: source modification is not allowed."
        return None

    def _audit(self, decision: SandboxDecision) -> None:
        self.audit_logger.append(
            actor=decision.request.actor,
            action=decision.request.action,
            resource=decision.request.resource,
            allowed=decision.allowed,
            reason=decision.reason,
            metadata={
                "component": "sandbox_guard",
                "operation": decision.request.operation,
                "filesystem": decision.request.filesystem,
                "network": decision.request.network,
            },
        )


__all__ = [
    "FilesystemMode",
    "NetworkMode",
    "SandboxDecision",
    "SandboxGuard",
    "SandboxRequest",
]
