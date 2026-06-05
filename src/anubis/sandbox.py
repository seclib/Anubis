from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from anubis.types import Task


class SandboxMode(StrEnum):
    READ_ONLY = "read_only"
    RESTRICTED = "restricted"
    PRIVILEGED = "privileged"


class NetworkPolicy(StrEnum):
    DENY = "deny"
    LOOPBACK = "loopback"
    ALLOWLIST = "allowlist"
    ALLOW = "allow"


class FilesystemPolicy(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    SCRATCH = "scratch"
    ALLOWLIST = "allowlist"


class PermissionEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    capability: str
    effect: PermissionEffect = PermissionEffect.ALLOW


@dataclass(frozen=True, slots=True)
class PermissionSet:
    agent_name: str
    grants: frozenset[CapabilityGrant]

    def __post_init__(self) -> None:
        object.__setattr__(self, "grants", frozenset(self.grants))

    def allows(self, capability: str) -> bool:
        matching = tuple(grant for grant in self.grants if grant.capability == capability)
        if not matching:
            return False
        return not any(grant.effect == PermissionEffect.DENY for grant in matching)


@dataclass(frozen=True, slots=True)
class IsolationProfile:
    name: str
    mode: SandboxMode = SandboxMode.RESTRICTED
    filesystem: FilesystemPolicy = FilesystemPolicy.SCRATCH
    network: NetworkPolicy = NetworkPolicy.DENY
    allowed_paths: tuple[str, ...] = field(default_factory=tuple)
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float | None = None
    memory_mb: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.memory_mb is not None and self.memory_mb < 1:
            raise ValueError("memory_mb must be at least 1")
        object.__setattr__(self, "allowed_paths", tuple(self.allowed_paths))
        object.__setattr__(self, "allowed_hosts", tuple(self.allowed_hosts))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    task: Task
    agent_name: str
    requested_capabilities: frozenset[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_capabilities", frozenset(self.requested_capabilities))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SandboxDecision:
    allowed: bool
    profile: IsolationProfile | None
    missing_capabilities: tuple[str, ...]
    explanation: str


class PermissionSystem:
    def __init__(self, permissions: tuple[PermissionSet, ...] = ()) -> None:
        self._permissions = {permission.agent_name: permission for permission in permissions}

    def grant(self, permission: PermissionSet) -> None:
        self._permissions[permission.agent_name] = permission

    def evaluate(self, request: SandboxRequest) -> tuple[str, ...]:
        permission = self._permissions.get(request.agent_name)
        if permission is None:
            return tuple(sorted(request.requested_capabilities))
        return tuple(
            sorted(
                capability
                for capability in request.requested_capabilities
                if not permission.allows(capability)
            )
        )


class SandboxPolicy:
    def __init__(
        self,
        *,
        default_profile: IsolationProfile | None = None,
        profiles_by_capability: Mapping[str, IsolationProfile] | None = None,
    ) -> None:
        self.default_profile = default_profile or IsolationProfile(name="restricted-default")
        self._profiles_by_capability = dict(profiles_by_capability or {})

    def profile_for(self, request: SandboxRequest) -> IsolationProfile:
        selected = self.default_profile
        for capability in sorted(request.requested_capabilities):
            selected = self._profiles_by_capability.get(capability, selected)
        return selected


class Sandbox:
    def __init__(
        self,
        *,
        permissions: PermissionSystem | None = None,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.permissions = permissions or PermissionSystem()
        self.policy = policy or SandboxPolicy()

    def authorize(self, request: SandboxRequest) -> SandboxDecision:
        missing = self.permissions.evaluate(request)
        if missing:
            return SandboxDecision(
                allowed=False,
                profile=None,
                missing_capabilities=missing,
                explanation=(
                    f"Sandbox denied task for agent '{request.agent_name}'; "
                    f"missing capabilities: {list(missing)}."
                ),
            )
        profile = self.policy.profile_for(request)
        return SandboxDecision(
            allowed=True,
            profile=profile,
            missing_capabilities=(),
            explanation=(
                f"Sandbox allowed task for agent '{request.agent_name}' "
                f"with profile '{profile.name}'."
            ),
        )


def default_sandbox() -> Sandbox:
    return Sandbox(
        policy=SandboxPolicy(
            default_profile=IsolationProfile(
                name="restricted-default",
                mode=SandboxMode.RESTRICTED,
                filesystem=FilesystemPolicy.SCRATCH,
                network=NetworkPolicy.DENY,
                timeout_seconds=30,
                memory_mb=256,
            )
        )
    )

