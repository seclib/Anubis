"""Deterministic planning engine for ANUBIS.

This module converts user input into a structured task graph and resolves that
graph into an ordered execution plan. It contains no task execution, agent
dispatch, sandbox control, or orchestration state management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from core.planner.dependency_resolver import DependencyResolver
from core.planner.task_graph import InputIntent, OrderedExecutionPlan, TaskGraph, TaskNode
from core.planner.validator import PlanValidator


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


@dataclass(frozen=True, slots=True)
class TaskBlueprint:
    """Template used by the planner to build task graph nodes."""

    task_id: str
    kind: str
    objective_template: str
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    depends_on: frozenset[str] = field(default_factory=frozenset)
    priority: int = 100
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.priority < 1:
            raise ValueError(f"task blueprint {self.task_id} priority must be positive")
        object.__setattr__(
            self,
            "required_capabilities",
            frozenset(sorted(item.strip() for item in self.required_capabilities if item.strip())),
        )
        object.__setattr__(
            self,
            "depends_on",
            frozenset(sorted(item.strip() for item in self.depends_on if item.strip())),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def instantiate(self, intent: InputIntent) -> TaskNode:
        objective = self.objective_template.format(
            objective=intent.objective,
            intent_kind=intent.kind,
        )
        metadata = {
            "intent_kind": intent.kind,
            "intent_objective": intent.objective,
            **dict(self.metadata),
        }
        return TaskNode(
            task_id=self.task_id,
            kind=self.kind,
            objective=objective,
            required_capabilities=self.required_capabilities,
            depends_on=self.depends_on,
            priority=self.priority,
            reason=self.reason,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class PlanningRule:
    """Maps an intent kind to deterministic task blueprints."""

    intent_kind: str
    steps: tuple[TaskBlueprint, ...]
    description: str = ""

    def __post_init__(self) -> None:
        intent_kind = self.intent_kind.strip()
        if not intent_kind:
            raise ValueError("planning rule intent_kind cannot be empty")
        if not self.steps:
            raise ValueError(f"planning rule {intent_kind} must define at least one step")
        object.__setattr__(self, "intent_kind", intent_kind)
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "description", self.description.strip())


@dataclass(slots=True)
class PlanningEngine:
    """Pure planning facade used by the orchestrator control plane."""

    rules: Mapping[str, PlanningRule] = field(default_factory=dict)
    resolver: DependencyResolver = field(default_factory=DependencyResolver)
    validator: PlanValidator = field(default_factory=PlanValidator)

    def __post_init__(self) -> None:
        if not self.rules:
            self.rules = {rule.intent_kind: rule for rule in default_planning_rules()}
        else:
            self.rules = dict(sorted(self.rules.items()))

    def infer_intent(self, user_input: str, intent_kind: str = "investigate_alert") -> InputIntent:
        objective = user_input.strip()
        if not objective:
            raise ValueError("user input cannot be empty")
        if intent_kind not in self.rules:
            intent_kind = "general_task"
        return InputIntent(
            kind=intent_kind,
            objective=objective,
            metadata={"source": "user_input"},
        )

    def create_task_graph(
        self,
        user_input: str | InputIntent,
        *,
        intent_kind: str = "investigate_alert",
    ) -> TaskGraph:
        intent = (
            user_input
            if isinstance(user_input, InputIntent)
            else self.infer_intent(user_input, intent_kind=intent_kind)
        )
        rule = self.rules.get(intent.kind)
        if rule is None:
            raise ValueError(f"no planning rule registered for intent kind: {intent.kind}")

        nodes = tuple(blueprint.instantiate(intent) for blueprint in rule.steps)
        graph = TaskGraph(
            graph_id=_stable_id("graph", intent.kind, intent.objective),
            intent=intent,
            nodes=nodes,
            metadata={"rule_description": rule.description},
        )
        self.validator.validate_graph(graph)
        return graph

    def plan(
        self,
        user_input: str | InputIntent,
        *,
        intent_kind: str = "investigate_alert",
    ) -> OrderedExecutionPlan:
        graph = self.create_task_graph(user_input, intent_kind=intent_kind)
        return self.resolver.resolve(graph)

    def register_rule(self, rule: PlanningRule) -> None:
        if rule.intent_kind in self.rules:
            raise ValueError(f"planning rule already registered: {rule.intent_kind}")
        next_rules = dict(self.rules)
        next_rules[rule.intent_kind] = rule
        self.rules = dict(sorted(next_rules.items()))


def default_planning_rules() -> tuple[PlanningRule, ...]:
    """Return deterministic built-in rules for safe local orchestration."""

    return (
        PlanningRule(
            intent_kind="general_task",
            description="Generic analysis workflow for inputs without a specialized rule.",
            steps=(
                TaskBlueprint(
                    task_id="clarify_objective",
                    kind="planning.analysis",
                    objective_template="Clarify the requested objective: {objective}",
                    required_capabilities=frozenset({"reason.plan"}),
                    priority=10,
                    reason="The system must first normalize the user objective.",
                ),
                TaskBlueprint(
                    task_id="structure_response",
                    kind="planning.synthesis",
                    objective_template="Structure a safe response plan for: {objective}",
                    required_capabilities=frozenset({"reason.synthesize"}),
                    depends_on=frozenset({"clarify_objective"}),
                    priority=20,
                    reason="A structured response depends on the clarified objective.",
                ),
            ),
        ),
        PlanningRule(
            intent_kind="investigate_alert",
            description="Safe investigation workflow for suspicious or defensive events.",
            steps=(
                TaskBlueprint(
                    task_id="collect_context",
                    kind="memory.recall",
                    objective_template="Collect relevant context for: {objective}",
                    required_capabilities=frozenset({"memory.read", "telemetry.read"}),
                    priority=10,
                    reason="Context must be gathered before analysis.",
                ),
                TaskBlueprint(
                    task_id="analyze_evidence",
                    kind="analysis.evaluate",
                    objective_template="Analyze evidence related to: {objective}",
                    required_capabilities=frozenset({"reason.analyze"}),
                    depends_on=frozenset({"collect_context"}),
                    priority=20,
                    reason="Evidence analysis depends on collected context.",
                ),
                TaskBlueprint(
                    task_id="recommend_response",
                    kind="policy.recommend",
                    objective_template="Recommend a controlled response for: {objective}",
                    required_capabilities=frozenset({"policy.evaluate", "reason.synthesize"}),
                    depends_on=frozenset({"analyze_evidence"}),
                    priority=30,
                    reason="Response recommendations require completed analysis.",
                ),
            ),
        ),
    )


def build_planning_engine(rules: Iterable[PlanningRule] | None = None) -> PlanningEngine:
    rule_map = {rule.intent_kind: rule for rule in (rules or default_planning_rules())}
    return PlanningEngine(rules=rule_map)


__all__ = [
    "PlanningEngine",
    "PlanningRule",
    "TaskBlueprint",
    "build_planning_engine",
    "default_planning_rules",
]
