"""Deny-by-default permission engine for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _freeze_strings(values: frozenset[str] | set[str] | tuple[str, ...] | list[str]) -> frozenset[str]:
    return frozenset(sorted(item.strip() for item in values if item and item.strip()))


class PermissionEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ActionRequest:
    """Structured action authorization request."""

    actor: str
    action: str
    resource: str
    required_permissions: frozenset[str] = field(default_factory=frozenset)
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        actor = self.actor.strip()
        action = self.action.strip()
        resource = self.resource.strip()
        if not actor:
            raise ValueError("actor cannot be empty")
        if not action:
            raise ValueError("action cannot be empty")
        if not resource:
            raise ValueError("resource cannot be empty")
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "resource", resource)
        object.__setattr__(self, "required_permissions", _freeze_strings(self.required_permissions))
        object.__setattr__(self, "context", _freeze_mapping(self.context))

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "required_permissions": sorted(self.required_permissions),
            "context": dict(self.context),
        }


@dataclass(frozen=True, slots=True)
class PermissionRule:
    """Explicit allow/deny rule scoped to one actor."""

    actor: str
    actions: frozenset[str]
    resources: frozenset[str]
    permissions: frozenset[str] = field(default_factory=frozenset)
    effect: PermissionEffect = PermissionEffect.ALLOW
    reason: str = ""

    def __post_init__(self) -> None:
        actor = self.actor.strip()
        if not actor:
            raise ValueError("rule actor cannot be empty")
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "actions", _freeze_strings(self.actions))
        object.__setattr__(self, "resources", _freeze_strings(self.resources))
        object.__setattr__(self, "permissions", _freeze_strings(self.permissions))
        object.__setattr__(self, "reason", self.reason.strip())
        if "*" in self.actions or "*" in self.resources or "*" in self.permissions:
            raise ValueError("wildcard permissions are not allowed")
        if not self.actions:
            raise ValueError("rule actions cannot be empty")
        if not self.resources:
            raise ValueError("rule resources cannot be empty")

    def matches(self, request: ActionRequest) -> bool:
        if self.actor != request.actor:
            return False
        if request.action not in self.actions:
            return False
        if request.resource not in self.resources:
            return False
        return request.required_permissions.issubset(self.permissions)


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    request: ActionRequest
    reason: str
    matched_rule: PermissionRule | None = None
    missing_permissions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_permissions", _freeze_strings(self.missing_permissions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "request": self.request.to_dict(),
            "reason": self.reason,
            "matched_rule": None if self.matched_rule is None else {
                "actor": self.matched_rule.actor,
                "actions": sorted(self.matched_rule.actions),
                "resources": sorted(self.matched_rule.resources),
                "permissions": sorted(self.matched_rule.permissions),
                "effect": self.matched_rule.effect,
                "reason": self.matched_rule.reason,
            },
            "missing_permissions": sorted(self.missing_permissions),
        }


class PermissionEngine:
    """Deterministic deny-by-default permission engine."""

    def __init__(self, rules: tuple[PermissionRule, ...] | None = None) -> None:
        self._rules: list[PermissionRule] = []
        for rule in rules or ():
            self.add_rule(rule)

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)
        self._rules.sort(
            key=lambda item: (
                item.actor,
                sorted(item.actions),
                sorted(item.resources),
                item.effect,
            )
        )

    def rules(self) -> tuple[PermissionRule, ...]:
        return tuple(self._rules)

    def validate(self, request: ActionRequest) -> PermissionDecision:
        matching_actor_rules = [rule for rule in self._rules if rule.actor == request.actor]
        explicit_denies = [
            rule for rule in matching_actor_rules
            if rule.effect == PermissionEffect.DENY
            and request.action in rule.actions
            and request.resource in rule.resources
        ]
        if explicit_denies:
            rule = explicit_denies[0]
            return PermissionDecision(
                allowed=False,
                request=request,
                reason=rule.reason or "Explicit deny rule matched.",
                matched_rule=rule,
            )

        for rule in matching_actor_rules:
            if rule.effect == PermissionEffect.ALLOW and rule.matches(request):
                return PermissionDecision(
                    allowed=True,
                    request=request,
                    reason=rule.reason or "Explicit allow rule matched.",
                    matched_rule=rule,
                )

        granted_permissions = frozenset().union(
            *(rule.permissions for rule in matching_actor_rules if rule.effect == PermissionEffect.ALLOW),
        ) if matching_actor_rules else frozenset()
        return PermissionDecision(
            allowed=False,
            request=request,
            reason="Denied by default: no explicit allow rule matched.",
            missing_permissions=request.required_permissions - granted_permissions,
        )


PermissionSystem = PermissionEngine


__all__ = [
    "ActionRequest",
    "PermissionDecision",
    "PermissionEffect",
    "PermissionEngine",
    "PermissionRule",
    "PermissionSystem",
]
