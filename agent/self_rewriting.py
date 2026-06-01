"""Validated self-rewriting patch pipeline for Anubis agents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent.multi_agent import (
    CODER_AGENT,
    DEBUGGER_AGENT,
    MEMORY_AGENT,
    ORCHESTRATOR_AGENT,
    PLANNER_AGENT,
    REVIEWER_AGENT,
    TESTER_AGENT,
)
from agent.self_improvement import analyze_performance, propose_strategy_improvements

CRITIC_AGENT = "critic_agent"
META_COGNITION_AGENT = "meta_cognition_agent"

PATCH_FIELDS = [
    "target_agent",
    "reason",
    "current_behavior",
    "proposed_change",
    "expected_improvement",
    "risk_assessment",
]

KNOWN_PATCH_TARGETS = {
    ORCHESTRATOR_AGENT,
    PLANNER_AGENT,
    CODER_AGENT,
    REVIEWER_AGENT,
    TESTER_AGENT,
    DEBUGGER_AGENT,
    MEMORY_AGENT,
    "retriever_agent",
    "writer_agent",
    "indexer_agent",
    "skill_engine",
    "loop_optimizer",
}

SELF_REWRITING_RULES = [
    "agents may propose patches but must not directly modify their own code",
    "patches require critic_agent and meta_cognition_agent validation before apply",
    "validated application records behavior updates instead of mutating source code",
    "prefer measurable improvement and low-risk, stability-preserving changes",
    "reject patches that create drift, vague behavior changes, or direct code mutation",
]


def create_self_rewriting_state() -> dict[str, Any]:
    """Create the runtime state for the self-rewriting governance layer."""
    return {
        "status": "ready",
        "rules": SELF_REWRITING_RULES,
        "patch_schema": {field: "string" for field in PATCH_FIELDS},
        "pending_patches": [],
        "validated_patches": [],
        "applied_patches": [],
        "rejected_patches": [],
    }


def normalize_self_rewrite_patch(value: Any) -> dict[str, str]:
    """Normalize arbitrary input into the strict self-rewrite patch schema."""
    source = value if isinstance(value, dict) else {}
    patch: dict[str, str] = {}
    for field in PATCH_FIELDS:
        patch[field] = str(source.get(field, "")).strip()
    return patch


def validate_patch_schema(patch: dict[str, Any]) -> dict[str, Any]:
    """Validate patch shape without applying the patch."""
    normalized = normalize_self_rewrite_patch(patch)
    missing = [field for field, value in normalized.items() if not value]
    unknown_target = (
        normalized["target_agent"] not in KNOWN_PATCH_TARGETS
        if normalized["target_agent"]
        else False
    )
    direct_mutation_terms = ("write source", "modify source", "edit code directly", "directly modify")
    direct_mutation = any(
        term in normalized["proposed_change"].lower()
        for term in direct_mutation_terms
    )

    issues: list[str] = []
    if missing:
        issues.append(f"missing required fields: {', '.join(missing)}")
    if unknown_target:
        issues.append(f"unknown target_agent: {normalized['target_agent']}")
    if direct_mutation:
        issues.append("proposed_change attempts direct source mutation")

    return {
        "success": not issues,
        "status": "approved" if not issues else "changes_requested",
        "patch": normalized,
        "issues": issues,
    }


def observe_self_rewrite_candidates(memory: dict[str, Any]) -> dict[str, Any]:
    """Observe performance and extract candidate self-rewrite signals."""
    analysis = analyze_performance(memory)
    suggestions = propose_strategy_improvements(memory)
    signals: list[str] = []

    if analysis["recurring_failures"]:
        signals.append("recurring_failures")
    if analysis["cycles_without_progress"] > 0:
        signals.append("cycles_without_progress")
    if analysis["consecutive_failures"] >= 2:
        signals.append("consecutive_failures")
    if analysis["success_rate"] < 0.6 and analysis["total_tool_calls"] >= 3:
        signals.append("low_tool_success_rate")

    return {
        "performance": analysis,
        "strategy_suggestions": suggestions,
        "signals": signals,
    }


def propose_self_rewrite_patch(memory: dict[str, Any], target_agent: str | None = None) -> dict[str, str]:
    """Generate a behavior patch proposal from observed agent performance."""
    observation = observe_self_rewrite_candidates(memory)
    performance = observation["performance"]
    suggestions = observation["strategy_suggestions"]
    recurring = performance["recurring_failures"]
    failed_tools = performance["most_failed_tools"]
    selected_target = target_agent or str(memory.get("last_agent") or ORCHESTRATOR_AGENT)

    if recurring:
        reason = f"Recurring failure pattern detected: {recurring[0]['pattern']}"
        current_behavior = "Agent may retry a previously failing tool path without first changing evidence or arguments."
        proposed_change = (
            "Before repeating a failed tool pattern, inspect context, verify paths or command scope, "
            "and switch strategy when the same failure appears twice."
        )
    elif failed_tools:
        tool = next(iter(failed_tools))
        reason = f"Tool failures concentrated around {tool}"
        current_behavior = f"Agent uses {tool} without enough preflight validation after failures."
        proposed_change = suggestions[0] if suggestions else "Add preflight validation before retrying the failed tool."
    elif performance["cycles_without_progress"] > 0 or performance["consecutive_failures"] >= 2:
        reason = "Loop progress stalled or failures are consecutive."
        current_behavior = "Agent can continue the same strategy after a no-progress cycle."
        proposed_change = "Force a strategy change and request fresh evidence after a no-progress cycle."
    else:
        reason = "No material inefficiency detected."
        current_behavior = "Current behavior is stable under recent observations."
        proposed_change = "Keep current behavior unchanged; do not apply a self-rewrite patch."

    expected_improvement = (
        "Reduce repeated failures and improve measurable tool success rate while preserving loop stability."
        if observation["signals"]
        else "No measurable improvement expected because no change is recommended."
    )
    risk_assessment = (
        "low: behavior-only guardrail; no direct source mutation; reversible by removing the approved patch record"
        if observation["signals"]
        else "low: no-op recommendation"
    )

    return normalize_self_rewrite_patch(
        {
            "target_agent": selected_target,
            "reason": reason,
            "current_behavior": current_behavior,
            "proposed_change": proposed_change,
            "expected_improvement": expected_improvement,
            "risk_assessment": risk_assessment,
        }
    )


def simulate_self_rewrite_patch(
    memory: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Simulate impact without mutating memory or source code."""
    before = deepcopy(memory)
    schema = validate_patch_schema(patch)
    observation = observe_self_rewrite_candidates(memory)
    performance = observation["performance"]
    has_signals = bool(observation["signals"])
    projected_success_rate = performance["success_rate"]
    if schema["success"] and has_signals:
        projected_success_rate = min(1.0, round(projected_success_rate + 0.15, 3))

    return {
        "success": schema["success"],
        "applied": False,
        "source_code_modified": False,
        "memory_modified": before != memory,
        "observed_signals": observation["signals"],
        "projected_success_rate": projected_success_rate,
        "expected_effects": [
            "fewer repeated tool retries",
            "earlier strategy changes after stalled cycles",
            "more explicit validation before behavior updates",
        ]
        if schema["success"] and has_signals
        else ["no behavior change simulated"],
        "risks": schema["issues"] or [schema["patch"]["risk_assessment"]],
    }


def build_patch_validation_requests(patch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build review payloads for critic_agent and meta_cognition_agent."""
    normalized = normalize_self_rewrite_patch(patch)
    return {
        CRITIC_AGENT: {
            "task": "Review the self-rewrite patch for correctness, safety, regression risk, and measurable value.",
            "patch": normalized,
            "required_decision": "approved | changes_requested | rejected",
        },
        META_COGNITION_AGENT: {
            "task": "Review the self-rewrite patch for behavioral drift, system stability, and alignment with observed evidence.",
            "patch": normalized,
            "required_decision": "approved | changes_requested | rejected",
        },
    }


def _normalize_validation_report(value: Any, reviewer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "agent": reviewer,
            "status": "changes_requested",
            "success": False,
            "reason": "validation report was not structured",
        }
    status = str(value.get("status", "approved" if value.get("success") else "changes_requested"))
    if status not in {"approved", "changes_requested", "rejected"}:
        status = "changes_requested"
    return {
        "agent": reviewer,
        "status": status,
        "success": bool(value.get("success", status == "approved")),
        "reason": str(value.get("reason", value.get("summary", ""))),
    }


def validate_self_rewrite_patch(
    patch: dict[str, Any],
    *,
    critic_report: dict[str, Any] | None = None,
    meta_cognition_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a patch through schema, critic, and meta-cognition gates."""
    schema = validate_patch_schema(patch)
    critic = _normalize_validation_report(
        critic_report or {
            "status": "approved" if schema["success"] else "changes_requested",
            "success": schema["success"],
            "reason": "deterministic critic gate based on patch schema and mutation safety",
        },
        CRITIC_AGENT,
    )
    meta = _normalize_validation_report(
        meta_cognition_report or {
            "status": "approved" if schema["success"] else "changes_requested",
            "success": schema["success"],
            "reason": "deterministic meta-cognition gate based on stability rules",
        },
        META_COGNITION_AGENT,
    )
    approved = schema["success"] and critic["success"] and meta["success"]

    return {
        "success": approved,
        "status": "approved" if approved else "changes_requested",
        "patch": schema["patch"],
        "schema_validation": schema,
        "critic_agent": critic,
        "meta_cognition_agent": meta,
        "reason": "patch validated by critic_agent and meta_cognition_agent"
        if approved
        else "patch requires revision before application",
    }


def apply_validated_self_rewrite_patch(
    memory: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Record an approved behavior patch; never mutate source code directly."""
    state = memory.setdefault("self_rewriting", create_self_rewriting_state())
    patch = normalize_self_rewrite_patch(validation.get("patch", {}))
    record = {
        "patch": patch,
        "validation": validation,
        "source_code_modified": False,
        "application_type": "validated_behavior_record",
    }

    if validation.get("success") is True and validation.get("status") == "approved":
        state.setdefault("validated_patches", []).append(patch)
        state.setdefault("applied_patches", []).append(record)
        state["status"] = "patch_applied"
        return {
            "success": True,
            "status": "applied",
            "applied": True,
            "source_code_modified": False,
            "patch": patch,
        }

    state.setdefault("rejected_patches", []).append(record)
    state["status"] = "patch_rejected"
    return {
        "success": False,
        "status": "rejected",
        "applied": False,
        "source_code_modified": False,
        "patch": patch,
    }


def run_self_rewriting_pipeline(memory: dict[str, Any]) -> dict[str, Any]:
    """Run observe, propose, simulate, validate, and conditional apply."""
    state = memory.setdefault("self_rewriting", create_self_rewriting_state())
    observation = observe_self_rewrite_candidates(memory)
    patch = propose_self_rewrite_patch(memory)
    simulation = simulate_self_rewrite_patch(memory, patch)
    validation_requests = build_patch_validation_requests(patch)
    validation = validate_self_rewrite_patch(patch)
    recommendation = "apply" if validation["success"] and observation["signals"] else "reject"
    application_validation = validation
    if validation["success"] and not observation["signals"]:
        application_validation = {
            **validation,
            "success": False,
            "status": "changes_requested",
            "reason": "no observed inefficiency requires a self-rewrite patch",
        }
    if not validation["success"]:
        recommendation = "revise"
    application = apply_validated_self_rewrite_patch(memory, application_validation)

    state.setdefault("pending_patches", []).append(patch)
    state["last_observation"] = observation
    state["last_patch"] = patch
    state["last_simulation"] = simulation
    state["last_validation"] = validation
    state["last_application"] = application
    state["last_recommendation"] = recommendation

    return {
        "observation": observation,
        "patch": patch,
        "simulation": simulation,
        "validation_requests": validation_requests,
        "validation": validation,
        "application": application,
        "recommendation": recommendation,
    }


__all__ = [
    "CRITIC_AGENT",
    "META_COGNITION_AGENT",
    "PATCH_FIELDS",
    "SELF_REWRITING_RULES",
    "apply_validated_self_rewrite_patch",
    "build_patch_validation_requests",
    "create_self_rewriting_state",
    "normalize_self_rewrite_patch",
    "observe_self_rewrite_candidates",
    "propose_self_rewrite_patch",
    "run_self_rewriting_pipeline",
    "simulate_self_rewrite_patch",
    "validate_patch_schema",
    "validate_self_rewrite_patch",
]
