"""Safe hot-swap runtime for self-modifying agent behavior.

This module lets agents propose behavior changes for registered runtime
functions without allowing arbitrary source mutation or dynamic code execution.
Approved patches update policy metadata and wrappers in the live registry; every
change is versioned and rollbackable.
"""

from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.self_rewriting import CRITIC_AGENT, META_COGNITION_AGENT

LOOP_OPTIMIZER_AGENT = "loop_optimizer"

PATCH_FIELDS = [
    "target_function",
    "reason",
    "current_behavior",
    "proposed_behavior",
    "expected_improvement",
    "risk_level",
]

SAFE_RISK_LEVELS = {"low", "medium"}
REJECTED_TERMS = {
    "exec(",
    "eval(",
    "compile(",
    "__import__",
    "subprocess",
    "os.system",
    "disable validation",
    "disable logging",
    "disable rollback",
    "skip critic",
    "bypass approval",
    "modify source",
    "write source",
}


def _now() -> float:
    return time.time()


def _patch_id(patch: dict[str, str]) -> str:
    raw = "|".join(patch[field] for field in PATCH_FIELDS)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_runtime_patch(value: Any) -> dict[str, str]:
    """Normalize arbitrary input into the runtime patch proposal schema."""
    source = value if isinstance(value, dict) else {}
    patch = {field: str(source.get(field, "")).strip() for field in PATCH_FIELDS}
    patch["risk_level"] = patch["risk_level"].lower()
    patch["patch_id"] = str(source.get("patch_id") or _patch_id(patch))
    return patch


@dataclass
class ToolUsageStrategy:
    """Policy applied around a registered function during hot-swap execution."""

    require_preflight: bool = False
    prefer_read_only: bool = False
    max_retries: int = 0
    notes: list[str] = field(default_factory=list)
    patch_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_preflight": self.require_preflight,
            "prefer_read_only": self.prefer_read_only,
            "max_retries": self.max_retries,
            "notes": list(self.notes),
            "patch_id": self.patch_id,
        }

    @classmethod
    def from_patch(cls, patch: dict[str, str], previous: "ToolUsageStrategy | None" = None) -> "ToolUsageStrategy":
        text = f"{patch['proposed_behavior']} {patch['expected_improvement']}".lower()
        strategy = deepcopy(previous) if previous else cls()
        if "preflight" in text or "validate" in text or "verify" in text:
            strategy.require_preflight = True
        if "read-only" in text or "read only" in text or "inspect before mutating" in text:
            strategy.prefer_read_only = True
        if "no retry" in text or "avoid retry" in text:
            strategy.max_retries = 0
        elif "retry" in text and strategy.max_retries == 0:
            strategy.max_retries = 1
        strategy.notes = [patch["proposed_behavior"]]
        strategy.patch_id = patch["patch_id"]
        return strategy


@dataclass
class RuntimeFunctionEntry:
    name: str
    function: Callable[..., Any]
    behavior: str
    strategy: ToolUsageStrategy = field(default_factory=ToolUsageStrategy)
    version: int = 1
    active_patch_ids: list[str] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "behavior": self.behavior,
            "strategy": self.strategy.to_dict(),
            "version": self.version,
            "active_patch_ids": list(self.active_patch_ids),
        }


class SelfObservationLayer:
    """Append-only decision/action log with compact success metrics."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def log_decision(self, *, function: str, decision: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "timestamp": _now(),
            "type": "decision",
            "function": function,
            "decision": decision,
            "metadata": metadata or {},
        }
        self.events.append(event)
        return event

    def log_action(
        self,
        *,
        function: str,
        success: bool,
        result: Any = None,
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "timestamp": _now(),
            "type": "action",
            "function": function,
            "success": success,
            "result": result,
            "error": error,
            "metadata": metadata or {},
        }
        self.events.append(event)
        return event

    def metrics(self) -> dict[str, Any]:
        actions = [event for event in self.events if event["type"] == "action"]
        successes = sum(1 for event in actions if event["success"])
        failures = len(actions) - successes
        by_function: dict[str, dict[str, int]] = {}
        for event in actions:
            item = by_function.setdefault(event["function"], {"success": 0, "failure": 0})
            item["success" if event["success"] else "failure"] += 1
        return {
            "decisions": sum(1 for event in self.events if event["type"] == "decision"),
            "actions": len(actions),
            "successes": successes,
            "failures": failures,
            "success_rate": round(successes / len(actions), 3) if actions else 1.0,
            "by_function": by_function,
        }


class VersionStore:
    """In-memory version snapshots for hot-swap rollback."""

    def __init__(self) -> None:
        self.snapshots: list[dict[str, Any]] = []

    def create_snapshot(self, entry: RuntimeFunctionEntry, patch: dict[str, str]) -> dict[str, Any]:
        snapshot = {
            "snapshot_id": f"{entry.name}:v{entry.version}:{patch['patch_id']}",
            "timestamp": _now(),
            "target_function": entry.name,
            "patch_id": patch["patch_id"],
            "entry": entry.snapshot(),
        }
        self.snapshots.append(deepcopy(snapshot))
        return snapshot

    def latest_for(self, target_function: str) -> dict[str, Any] | None:
        for snapshot in reversed(self.snapshots):
            if snapshot["target_function"] == target_function:
                return deepcopy(snapshot)
        return None


class DynamicFunctionRegistry:
    """Live function registry that applies approved policy hot-swaps."""

    def __init__(self, observer: SelfObservationLayer | None = None) -> None:
        self.observer = observer or SelfObservationLayer()
        self._entries: dict[str, RuntimeFunctionEntry] = {}

    def register(
        self,
        name: str,
        function: Callable[..., Any],
        *,
        behavior: str = "",
        strategy: ToolUsageStrategy | None = None,
    ) -> None:
        self._entries[name] = RuntimeFunctionEntry(
            name=name,
            function=function,
            behavior=behavior or getattr(function, "__doc__", "") or name,
            strategy=strategy or ToolUsageStrategy(),
        )

    def has(self, name: str) -> bool:
        return name in self._entries

    def get(self, name: str) -> RuntimeFunctionEntry:
        return self._entries[name]

    def manifest(self) -> list[dict[str, Any]]:
        return [entry.snapshot() for entry in self._entries.values()]

    def execute(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if name not in self._entries:
            return {"success": False, "error": f"unknown runtime function: {name}"}
        entry = self._entries[name]
        strategy = entry.strategy
        self.observer.log_decision(
            function=name,
            decision="execute_runtime_function",
            metadata={"version": entry.version, "strategy": strategy.to_dict()},
        )

        if strategy.prefer_read_only and _looks_mutating(name):
            error = "read-only strategy blocked mutating function"
            self.observer.log_action(function=name, success=False, error=error)
            return {"success": False, "error": error, "blocked_by_strategy": True}
        if strategy.require_preflight and not args and not kwargs:
            error = "preflight validation failed: arguments are required"
            self.observer.log_action(function=name, success=False, error=error)
            return {"success": False, "error": error, "blocked_by_strategy": True}

        attempts = max(1, strategy.max_retries + 1)
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                result = entry.function(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - runtime boundary records all failures.
                last_error = str(exc)
                self.observer.log_action(
                    function=name,
                    success=False,
                    error=last_error,
                    metadata={"attempt": attempt},
                )
                continue
            self.observer.log_action(
                function=name,
                success=True,
                result=result,
                metadata={"attempt": attempt},
            )
            return {"success": True, "output": result, "attempts": attempt, "version": entry.version}
        return {"success": False, "error": last_error, "attempts": attempts, "version": entry.version}

    def hot_swap(self, patch: dict[str, str]) -> RuntimeFunctionEntry:
        entry = self.get(patch["target_function"])
        entry.behavior = patch["proposed_behavior"]
        entry.strategy = ToolUsageStrategy.from_patch(patch, entry.strategy)
        entry.version += 1
        entry.active_patch_ids.append(patch["patch_id"])
        return entry

    def restore_snapshot(self, snapshot: dict[str, Any]) -> RuntimeFunctionEntry:
        target = snapshot["target_function"]
        entry = self.get(target)
        previous = snapshot["entry"]
        strategy_payload = previous.get("strategy", {})
        entry.behavior = previous["behavior"]
        entry.strategy = ToolUsageStrategy(
            require_preflight=bool(strategy_payload.get("require_preflight")),
            prefer_read_only=bool(strategy_payload.get("prefer_read_only")),
            max_retries=int(strategy_payload.get("max_retries", 0) or 0),
            notes=list(strategy_payload.get("notes", [])),
            patch_id=str(strategy_payload.get("patch_id", "")),
        )
        entry.version = int(previous["version"])
        entry.active_patch_ids = list(previous.get("active_patch_ids", []))
        return entry


def _looks_mutating(name: str) -> bool:
    return any(token in name for token in ("write", "delete", "mutate", "apply", "commit", "swap"))


def validate_runtime_patch_schema(patch: dict[str, Any], registry: DynamicFunctionRegistry) -> dict[str, Any]:
    normalized = normalize_runtime_patch(patch)
    issues: list[str] = []
    missing = [field for field in PATCH_FIELDS if not normalized[field]]
    if missing:
        issues.append(f"missing required fields: {', '.join(missing)}")
    if normalized["target_function"] and not registry.has(normalized["target_function"]):
        issues.append(f"unknown target_function: {normalized['target_function']}")
    if normalized["risk_level"] not in SAFE_RISK_LEVELS:
        issues.append(f"unsupported risk_level: {normalized['risk_level']}")
    proposed = normalized["proposed_behavior"].lower()
    blocked_terms = sorted(term for term in REJECTED_TERMS if term in proposed)
    if blocked_terms:
        issues.append(f"unsafe proposed_behavior terms: {', '.join(blocked_terms)}")
    if len(normalized["proposed_behavior"].split()) < 4:
        issues.append("proposed_behavior is too vague")
    return {
        "success": not issues,
        "status": "approved" if not issues else "changes_requested",
        "patch": normalized,
        "issues": issues,
    }


def deterministic_critic_review(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent": CRITIC_AGENT,
        "success": schema["success"],
        "status": "approved" if schema["success"] else "changes_requested",
        "reason": "critic gate checks patch shape, target existence, risk, and unsafe behavior terms",
    }


def deterministic_meta_cognition_review(schema: dict[str, Any]) -> dict[str, Any]:
    patch = schema["patch"]
    drift_terms = ("ignore previous", "always", "never ask", "all tools")
    drift = [term for term in drift_terms if term in patch["proposed_behavior"].lower()]
    success = schema["success"] and not drift
    return {
        "agent": META_COGNITION_AGENT,
        "success": success,
        "status": "approved" if success else "changes_requested",
        "reason": "meta-cognition gate checks behavioral drift and system alignment",
        "drift_terms": drift,
    }


def deterministic_loop_optimizer_review(schema: dict[str, Any], registry: DynamicFunctionRegistry) -> dict[str, Any]:
    patch = schema["patch"]
    entry = registry.get(patch["target_function"]) if registry.has(patch["target_function"]) else None
    too_many_active = bool(entry and len(entry.active_patch_ids) >= 5)
    success = schema["success"] and not too_many_active
    return {
        "agent": LOOP_OPTIMIZER_AGENT,
        "success": success,
        "status": "approved" if success else "changes_requested",
        "reason": "loop optimizer gate checks stability and active hot-swap pressure",
        "too_many_active_patches": too_many_active,
    }


def validate_runtime_patch(
    patch: dict[str, Any],
    registry: DynamicFunctionRegistry,
    *,
    critic_report: dict[str, Any] | None = None,
    meta_cognition_report: dict[str, Any] | None = None,
    loop_optimizer_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema = validate_runtime_patch_schema(patch, registry)
    critic = critic_report or deterministic_critic_review(schema)
    meta = meta_cognition_report or deterministic_meta_cognition_review(schema)
    optimizer = loop_optimizer_report or deterministic_loop_optimizer_review(schema, registry)
    approved = schema["success"] and critic.get("success") and meta.get("success") and optimizer.get("success")
    return {
        "success": bool(approved),
        "status": "approved" if approved else "changes_requested",
        "patch": schema["patch"],
        "schema_validation": schema,
        CRITIC_AGENT: critic,
        META_COGNITION_AGENT: meta,
        LOOP_OPTIMIZER_AGENT: optimizer,
    }


def apply_runtime_patch(
    patch: dict[str, Any],
    registry: DynamicFunctionRegistry,
    versions: VersionStore,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validation or validate_runtime_patch(patch, registry)
    normalized = validation["patch"]
    if not validation["success"]:
        return {
            "success": False,
            "status": "rejected",
            "patch": normalized,
            "validation": validation,
        }
    snapshot = versions.create_snapshot(registry.get(normalized["target_function"]), normalized)
    entry = registry.hot_swap(normalized)
    registry.observer.log_decision(
        function=normalized["target_function"],
        decision="hot_swap_runtime_behavior",
        metadata={"patch_id": normalized["patch_id"], "snapshot_id": snapshot["snapshot_id"]},
    )
    return {
        "success": True,
        "status": "applied",
        "patch": normalized,
        "validation": validation,
        "snapshot": snapshot,
        "new_version": entry.version,
        "strategy": entry.strategy.to_dict(),
    }


def rollback_runtime_patch(target_function: str, registry: DynamicFunctionRegistry, versions: VersionStore) -> dict[str, Any]:
    snapshot = versions.latest_for(target_function)
    if not snapshot:
        return {"success": False, "status": "not_found", "target_function": target_function}
    entry = registry.restore_snapshot(snapshot)
    registry.observer.log_decision(
        function=target_function,
        decision="rollback_runtime_behavior",
        metadata={"snapshot_id": snapshot["snapshot_id"], "restored_version": entry.version},
    )
    return {
        "success": True,
        "status": "rolled_back",
        "target_function": target_function,
        "snapshot": snapshot,
        "version": entry.version,
    }


def runtime_architecture() -> dict[str, Any]:
    """Describe the self-modifying runtime architecture for control surfaces."""
    return {
        "agent_core": "registered runtime functions execute tasks and tools through DynamicFunctionRegistry",
        "self_observation_layer": "SelfObservationLayer records every decision and action with success/failure metrics",
        "patch_generation_system": {"schema": {field: "string" for field in PATCH_FIELDS}},
        "validation_pipeline": [CRITIC_AGENT, META_COGNITION_AGENT, LOOP_OPTIMIZER_AGENT],
        "hot_swap_execution": "approved patches update behavior policy wrappers without source mutation or restart",
        "versioning": "VersionStore snapshots pre-swap function behavior and supports rollback by target_function",
        "safety_model": [
            "no arbitrary Python code in patches",
            "known target function required",
            "low or medium risk only",
            "critic, meta-cognition, and loop optimizer gates must all approve",
            "rollback snapshot created before every hot-swap",
        ],
    }


__all__ = [
    "DynamicFunctionRegistry",
    "LOOP_OPTIMIZER_AGENT",
    "PATCH_FIELDS",
    "SelfObservationLayer",
    "ToolUsageStrategy",
    "VersionStore",
    "apply_runtime_patch",
    "normalize_runtime_patch",
    "rollback_runtime_patch",
    "runtime_architecture",
    "validate_runtime_patch",
    "validate_runtime_patch_schema",
]
