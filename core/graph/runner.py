"""Deterministic directed graph runner for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.graph.node import GraphNode, NodeResult
from core.graph.state_engine import StateEngine
from core.graph.state import (
    GraphError,
    GraphRunStatus,
    GraphState,
    NodeRunStatus,
    NodeTrace,
    utcnow,
)
from core.observability.logger import StructuredLogger
from core.observability.tracer import SpanStatus, Tracer


def _read_path(payload: Mapping[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        return None
    return current


@dataclass(frozen=True, slots=True)
class RouteCondition:
    """Declarative deterministic condition for conditional graph flow."""

    field_path: str
    equals: Any = True

    def __post_init__(self) -> None:
        if not self.field_path.strip():
            raise ValueError("route condition field_path cannot be empty")
        object.__setattr__(self, "field_path", self.field_path.strip())

    def matches(self, state: GraphState) -> bool:
        return _read_path(state.to_dict(), self.field_path) == self.equals

    def to_dict(self) -> dict[str, Any]:
        return {"field_path": self.field_path, "equals": self.equals}


@dataclass(frozen=True, slots=True)
class ConditionalRoute:
    """Named conditional edge evaluated in deterministic declaration order."""

    name: str
    target: str
    condition: RouteCondition
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("conditional route name cannot be empty")
        if not self.target.strip():
            raise ValueError("conditional route target cannot be empty")
        if self.priority < 1:
            raise ValueError("conditional route priority must be positive")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "target", self.target.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "condition": self.condition.to_dict(),
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class RouteDecision:
    source: str
    target: str | None
    route_name: str
    conditional: bool
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "route_name": self.route_name,
            "conditional": self.conditional,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class GraphDebugReport:
    run_id: str
    status: GraphRunStatus
    execution_path: tuple[str, ...]
    route_decisions: tuple[RouteDecision, ...]
    state_versions: tuple[Mapping[str, Any], ...]
    node_traces: tuple[Mapping[str, Any], ...]
    log_records: tuple[Mapping[str, Any], ...]
    errors: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_path", tuple(self.execution_path))
        object.__setattr__(self, "route_decisions", tuple(self.route_decisions))
        object.__setattr__(self, "state_versions", tuple(self.state_versions))
        object.__setattr__(self, "node_traces", tuple(self.node_traces))
        object.__setattr__(self, "log_records", tuple(self.log_records))
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "execution_path": self.execution_path,
            "route_decisions": tuple(route.to_dict() for route in self.route_decisions),
            "state_versions": tuple(dict(item) for item in self.state_versions),
            "node_traces": tuple(dict(item) for item in self.node_traces),
            "log_records": tuple(dict(item) for item in self.log_records),
            "errors": tuple(dict(item) for item in self.errors),
        }


@dataclass(frozen=True, slots=True)
class GraphDefinition:
    entrypoint: str
    terminal: str
    edges: Mapping[str, str]
    conditional_edges: Mapping[str, tuple[ConditionalRoute, ...]] = field(default_factory=dict)
    max_steps: int = 100

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("graph max_steps must be positive")
        object.__setattr__(self, "edges", dict(self.edges))
        object.__setattr__(
            self,
            "conditional_edges",
            {
                source: tuple(sorted(routes, key=lambda route: (route.priority, route.name)))
                for source, routes in self.conditional_edges.items()
            },
        )

    def next_node(self, current: str) -> str | None:
        return self.edges.get(current)

    def decide_next(self, current: str, state: GraphState) -> RouteDecision:
        for route in self.conditional_edges.get(current, ()):
            if route.condition.matches(state):
                return RouteDecision(
                    source=current,
                    target=route.target,
                    route_name=route.name,
                    conditional=True,
                    explanation=(
                        f"Conditional route '{route.name}' matched "
                        f"{route.condition.field_path} == {route.condition.equals!r}."
                    ),
                )
        target = self.next_node(current)
        return RouteDecision(
            source=current,
            target=target,
            route_name="default",
            conditional=False,
            explanation="Default deterministic edge selected.",
        )


class DeterministicGraphRunner:
    """Executes a directed graph with one deterministic successor per node."""

    def __init__(
        self,
        *,
        nodes: Mapping[str, GraphNode],
        definition: GraphDefinition,
        logger: StructuredLogger | None = None,
        tracer: Tracer | None = None,
        state_engine: StateEngine | None = None,
    ) -> None:
        self.nodes = dict(nodes)
        self.definition = definition
        self.logger = logger or StructuredLogger()
        self.tracer = tracer or Tracer()
        self.state_engine = state_engine or StateEngine()
        self._route_decisions: dict[str, list[RouteDecision]] = {}
        self._final_states: dict[str, GraphState] = {}
        self._validate()

    def run(self, state: GraphState) -> GraphState:
        trace_id = state.run_id
        graph_span = self.tracer.start_span(
            name="graph.run",
            component="core.graph",
            trace_id=trace_id,
            attributes={"entrypoint": self.definition.entrypoint},
        )
        self.state_engine.register_run(state)
        current_name: str | None = self.definition.entrypoint
        next_state = state.with_updates(status=GraphRunStatus.RUNNING)
        step_count = 0
        self._route_decisions[state.run_id] = []
        self._record_state(
            next_state,
            action="state.graph.running",
            reason="Graph runner marked the run as active.",
        )

        try:
            while current_name is not None:
                step_count += 1
                if step_count > self.definition.max_steps:
                    raise RuntimeError(
                        f"graph exceeded deterministic max_steps limit: {self.definition.max_steps}"
                    )
                node = self.nodes[current_name]
                next_state = self._run_node(node, next_state)
                self._record_state(
                    next_state,
                    action=f"state.node.{node.name}",
                    reason=f"Graph node '{node.name}' produced a new immutable state.",
                )
                if next_state.status == GraphRunStatus.FAILED:
                    break
                if current_name == self.definition.terminal:
                    next_state = next_state.with_updates(status=GraphRunStatus.SUCCEEDED)
                    self._record_state(
                        next_state,
                        action="state.graph.succeeded",
                        reason="Graph runner marked the terminal state as succeeded.",
                    )
                    break
                route_decision = self.definition.decide_next(current_name, next_state)
                self._route_decisions[state.run_id].append(route_decision)
                self._log_route_decision(next_state, route_decision, graph_span.span_id)
                current_name = route_decision.target
                if current_name is None:
                    raise RuntimeError("graph ended before terminal node")
        except Exception as exc:
            error = GraphError(
                node=current_name or "graph",
                error_type=type(exc).__name__,
                message=str(exc),
            )
            next_state = next_state.append_error(error)
            self._record_state(
                next_state,
                action="state.graph.failed",
                reason="Graph runner captured an unhandled graph-level error.",
            )
            self.logger.error(
                component="core.graph",
                action="graph.failed",
                message="Graph execution failed with a structured error.",
                trace_id=trace_id,
                span_id=graph_span.span_id,
                error=exc,
                metadata={"node": current_name},
            )
            self.tracer.finish_span(graph_span.span_id, status=SpanStatus.ERROR, error=exc)
            self._final_states[state.run_id] = next_state
            return next_state

        self.tracer.finish_span(
            graph_span.span_id,
            status=SpanStatus.OK if next_state.status == GraphRunStatus.SUCCEEDED else SpanStatus.ERROR,
            attributes={"status": next_state.status.value, "path": next_state.execution_path},
        )
        self._final_states[state.run_id] = next_state
        return next_state

    def _run_node(self, node: GraphNode, state: GraphState) -> GraphState:
        started_at = utcnow()
        span = self.tracer.start_span(
            name=f"node.{node.name}",
            component="core.graph.node",
            trace_id=state.run_id,
            attributes={"node": node.name},
        )
        input_keys = tuple(sorted(state.to_dict().keys()))
        self.logger.info(
            component="core.graph",
            action="node.started",
            message=f"Graph node started: {node.name}",
            trace_id=state.run_id,
            span_id=span.span_id,
            metadata={"node": node.name},
        )

        try:
            result = node.run(state)
            self._validate_result(result)
            completed_at = utcnow()
            trace = NodeTrace(
                sequence=len(state.traces) + 1,
                node=node.name,
                status=NodeRunStatus.SUCCEEDED,
                input_keys=input_keys,
                output_keys=tuple(sorted(result.outputs.keys())),
                explanation=result.explanation,
                started_at=started_at,
                completed_at=completed_at,
            )
            self.tracer.finish_span(
                span.span_id,
                status=SpanStatus.OK,
                attributes={"output_keys": trace.output_keys},
            )
            self.logger.info(
                component="core.graph",
                action="node.succeeded",
                message=f"Graph node completed: {node.name}",
                trace_id=state.run_id,
                span_id=span.span_id,
                metadata={"node": node.name, "output_keys": trace.output_keys},
            )
            return result.state.append_trace(trace)
        except Exception as exc:
            completed_at = utcnow()
            error = GraphError(
                node=node.name,
                error_type=type(exc).__name__,
                message=str(exc),
                recoverable=False,
            )
            trace = NodeTrace(
                sequence=len(state.traces) + 1,
                node=node.name,
                status=NodeRunStatus.FAILED,
                input_keys=input_keys,
                output_keys=(),
                explanation="Node failed and graph execution stopped.",
                started_at=started_at,
                completed_at=completed_at,
                error=error,
            )
            self.tracer.finish_span(span.span_id, status=SpanStatus.ERROR, error=exc)
            self.logger.error(
                component="core.graph",
                action="node.failed",
                message=f"Graph node failed: {node.name}",
                trace_id=state.run_id,
                span_id=span.span_id,
                error=exc,
                metadata={"node": node.name},
            )
            return state.append_trace(trace).append_error(error)

    def _validate(self) -> None:
        if self.definition.entrypoint not in self.nodes:
            raise ValueError("graph entrypoint must reference a registered node")
        if self.definition.terminal not in self.nodes:
            raise ValueError("graph terminal must reference a registered node")
        for source, target in self.definition.edges.items():
            if source not in self.nodes:
                raise ValueError(f"edge source is not a registered node: {source}")
            if target not in self.nodes:
                raise ValueError(f"edge target is not a registered node: {target}")
        for source, routes in self.definition.conditional_edges.items():
            if source not in self.nodes:
                raise ValueError(f"conditional edge source is not a registered node: {source}")
            for route in routes:
                if route.target not in self.nodes:
                    raise ValueError(
                        f"conditional edge target is not a registered node: {route.target}"
                    )

    @staticmethod
    def _validate_result(result: NodeResult) -> None:
        if not isinstance(result, NodeResult):
            raise TypeError("graph nodes must return NodeResult")

    def _record_state(self, state: GraphState, *, action: str, reason: str) -> None:
        self.state_engine.transition_run(
            state,
            actor="core.graph.runner",
            action=action,
            reason=reason,
        )

    def _log_route_decision(
        self,
        state: GraphState,
        route_decision: RouteDecision,
        span_id: str,
    ) -> None:
        self.logger.info(
            component="core.graph",
            action="edge.selected",
            message=f"Graph edge selected: {route_decision.source} -> {route_decision.target}",
            trace_id=state.run_id,
            span_id=span_id,
            metadata=route_decision.to_dict(),
        )

    def debug_report(self, run_id: str) -> GraphDebugReport:
        state = self._final_states.get(run_id)
        if state is None:
            state = self.state_engine.current.get_run(run_id)
        return GraphDebugReport(
            run_id=run_id,
            status=state.status,
            execution_path=state.execution_path,
            route_decisions=tuple(self._route_decisions.get(run_id, ())),
            state_versions=tuple(
                {
                    "version": version.version,
                    "state_hash": version.state_hash,
                    "transition": (
                        None if version.transition is None else version.transition.to_dict()
                    ),
                }
                for version in self.state_engine.history_for_run(run_id)
            ),
            node_traces=tuple(trace.to_dict() for trace in state.traces),
            log_records=tuple(
                record.to_dict()
                for record in self.logger.records()
                if record.trace_id == run_id
            ),
            errors=tuple(error.to_dict() for error in state.errors),
        )


__all__ = [
    "ConditionalRoute",
    "DeterministicGraphRunner",
    "GraphDebugReport",
    "GraphDefinition",
    "RouteCondition",
    "RouteDecision",
]
