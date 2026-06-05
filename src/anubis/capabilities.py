from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class CapabilityId(StrEnum):
    TASK_UNDERSTANDING = "task_understanding"
    POST_ACTION_REFLECTION = "post_action_reflection"
    SAFE_PATCH_PROPOSAL = "safe_patch_proposal"
    EXPLOITABLE_MEMORY = "exploitable_memory"
    SELF_DEFENSE = "self_defense"
    SWARM_EMERGENCE = "swarm_emergence"


@dataclass(frozen=True, slots=True)
class ComponentEvidence:
    module: str
    symbol: str
    responsibility: str

    @property
    def dotted_path(self) -> str:
        return f"{self.module}.{self.symbol}"


@dataclass(frozen=True, slots=True)
class Capability:
    id: CapabilityId
    name: str
    promise: str
    evidence: tuple[ComponentEvidence, ...]
    control_points: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "control_points", tuple(self.control_points))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CapabilityVerification:
    capability_id: CapabilityId
    available: bool
    checked_components: tuple[str, ...]
    missing_components: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_components", tuple(self.checked_components))
        object.__setattr__(self, "missing_components", tuple(self.missing_components))


class CapabilityManifest:
    """Executable capability map for ANUBIS self-identity."""

    def __init__(self, capabilities: Sequence[Capability] | None = None) -> None:
        self._capabilities = {
            capability.id: capability for capability in capabilities or default_capabilities()
        }

    def all(self) -> tuple[Capability, ...]:
        return tuple(
            self._capabilities[capability_id]
            for capability_id in sorted(self._capabilities)
        )

    def get(self, capability_id: CapabilityId | str) -> Capability:
        return self._capabilities[CapabilityId(capability_id)]

    def verify(self) -> tuple[CapabilityVerification, ...]:
        return tuple(self.verify_one(capability.id) for capability in self.all())

    def verify_one(self, capability_id: CapabilityId | str) -> CapabilityVerification:
        capability = self.get(capability_id)
        checked: list[str] = []
        missing: list[str] = []

        for evidence in capability.evidence:
            checked.append(evidence.dotted_path)
            try:
                module = importlib.import_module(evidence.module)
            except ImportError:
                missing.append(evidence.dotted_path)
                continue
            if not hasattr(module, evidence.symbol):
                missing.append(evidence.dotted_path)

        return CapabilityVerification(
            capability_id=capability.id,
            available=not missing,
            checked_components=tuple(checked),
            missing_components=tuple(missing),
        )

    def explain(self, capability_id: CapabilityId | str) -> tuple[str, ...]:
        capability = self.get(capability_id)
        lines = [
            f"{capability.name}: {capability.promise}",
            "Control points: " + ", ".join(capability.control_points),
        ]
        lines.extend(
            f"{item.dotted_path}: {item.responsibility}" for item in capability.evidence
        )
        return tuple(lines)


def default_capabilities() -> tuple[Capability, ...]:
    return (
        Capability(
            id=CapabilityId.TASK_UNDERSTANDING,
            name="Comprendre ses propres taches",
            promise="Transformer un stimulus en intention, strategie et taches routables.",
            evidence=(
                ComponentEvidence(
                    "anubis.core_life.brain.intent_inference",
                    "IntentInference",
                    "Converts prompt-like stimulus into an explicit Goal.",
                ),
                ComponentEvidence(
                    "anubis.planner",
                    "PlanningEngine",
                    "Decomposes goals into deterministic, explainable plan steps.",
                ),
                ComponentEvidence(
                    "anubis.core_life.metabolism.task_digestion",
                    "TaskDigestion",
                    "Turns goals into executable Task objects.",
                ),
            ),
            control_points=("goal.kind", "plan.explanation", "task.required_capabilities"),
        ),
        Capability(
            id=CapabilityId.POST_ACTION_REFLECTION,
            name="Reflechir apres action",
            promise="Analyze event history after execution and ask whether behavior improved.",
            evidence=(
                ComponentEvidence(
                    "anubis.core_life.brain.reflection_engine",
                    "ReflectionEngine",
                    "Runs post-action reflection over recorded events.",
                ),
                ComponentEvidence(
                    "anubis.self_improvement",
                    "PerformanceAnalyzer",
                    "Detects task failures, sandbox denials, kill switches, and architecture signals.",
                ),
            ),
            control_points=("event replay", "performance findings", "reflection report"),
        ),
        Capability(
            id=CapabilityId.SAFE_PATCH_PROPOSAL,
            name="Proposer des patchs controles",
            promise="Generate reviewable Git-style diffs; never apply source changes at runtime.",
            evidence=(
                ComponentEvidence(
                    "anubis.self_improvement",
                    "UpgradePlanner",
                    "Turns performance and architecture findings into upgrade proposals.",
                ),
                ComponentEvidence(
                    "anubis.self_improvement",
                    "PatchGenerationEngine",
                    "Generates safe simulated patch proposals for human review.",
                ),
                ComponentEvidence(
                    "anubis.architecture",
                    "PullRequestSystem",
                    "Validates base hashes and emits diffs without writing files.",
                ),
            ),
            control_points=("human approval", "simulation.safe", "base_hash", "patch diff"),
        ),
        Capability(
            id=CapabilityId.EXPLOITABLE_MEMORY,
            name="Se souvenir",
            promise="Promote logs and execution episodes into scoped, searchable memory.",
            evidence=(
                ComponentEvidence(
                    "anubis.core_life.memory_life.episodic_memory",
                    "EpisodicMemory",
                    "Stores execution episodes as task-scoped memory records.",
                ),
                ComponentEvidence(
                    "anubis.memory",
                    "SharedMemory",
                    "Enforces memory isolation, storage policy, conflict handling, and vector sync.",
                ),
                ComponentEvidence(
                    "anubis.retrieval",
                    "QueryRouter",
                    "Routes semantic queries over memory-backed vector stores.",
                ),
            ),
            control_points=("memory scope", "sensitivity", "vector sync cursor"),
        ),
        Capability(
            id=CapabilityId.SELF_DEFENSE,
            name="Se defendre",
            promise="Score suspicious behavior and trigger kill-switch decisions on anomalies.",
            evidence=(
                ComponentEvidence(
                    "anubis.safety",
                    "SafetyMonitor",
                    "Scores agent behavior and emits anomaly or kill-switch events.",
                ),
                ComponentEvidence(
                    "anubis.core_life.immune_system.kill_switch",
                    "KillSwitchDecision",
                    "Represents defensive shutdown decisions.",
                ),
                ComponentEvidence(
                    "anubis.sandbox",
                    "Sandbox",
                    "Mediates task permissions before execution.",
                ),
            ),
            control_points=("sandbox decision", "agent behavior score", "kill switch reason"),
        ),
        Capability(
            id=CapabilityId.SWARM_EMERGENCE,
            name="Emerger des comportements swarm",
            promise="Assign, score, replace, and rebalance agents as conditions change.",
            evidence=(
                ComponentEvidence(
                    "anubis.swarm",
                    "SwarmCoordinator",
                    "Assigns roles, resolves consensus, scores performance, and replaces agents.",
                ),
                ComponentEvidence(
                    "anubis.agents",
                    "AgentRegistry",
                    "Registers available agents and tracks runtime capacity.",
                ),
                ComponentEvidence(
                    "anubis.orchestrator",
                    "Orchestrator",
                    "Spawns task executions and manages agent lifecycle events.",
                ),
            ),
            control_points=("role assignment", "performance score", "agent replacement"),
        ),
    )
