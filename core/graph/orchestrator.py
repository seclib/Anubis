"""Graph-based ANUBIS orchestrator facade."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Mapping

from core.agents import build_default_agent_registry
from core.graph.node import GraphNode
from core.graph.nodes import (
    AgentDispatchNode,
    ExecutionSandboxNode,
    InputNode,
    MemoryNode,
    OutputNode,
    PlannerNode,
    ReflectionNode,
)
from core.graph.runner import DeterministicGraphRunner, GraphDebugReport, GraphDefinition
from core.graph.state_engine import GlobalSystemState, StateEngine
from core.graph.state import GraphRunStatus, GraphState
from core.memory import MemoryManager
from core.observability.logger import StructuredLogger
from core.observability.tracer import Tracer
from core.planner import build_planning_engine


GRAPH_NODE_ORDER = (
    "input",
    "planner",
    "agent_dispatch",
    "execution_sandbox",
    "memory",
    "reflection",
    "output",
)


@dataclass(frozen=True, slots=True)
class GraphExecutionResult:
    state: GraphState
    global_state: GlobalSystemState

    @property
    def succeeded(self) -> bool:
        return self.state.status == GraphRunStatus.SUCCEEDED

    def to_dict(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        payload["succeeded"] = self.succeeded
        payload["goal"] = self.state.stimulus
        payload["plan_id"] = self.state.plan.get("graph_id")
        payload["task_ids"] = tuple(self.state.plan.get("ordered_task_ids", ()))
        payload["final_output"] = dict(self.state.output)
        payload["state_history"] = tuple(
            version.to_dict()
            for version in self.global_state.history
            if version.run_id == self.state.run_id
        )
        payload["state_transitions"] = tuple(
            transition.to_dict()
            for transition in self.global_state.transitions
            if transition.run_id == self.state.run_id
        )
        payload["architecture"] = graph_architecture_design()
        return payload


@dataclass(slots=True)
class GraphOrchestrator:
    runner: DeterministicGraphRunner
    logger: StructuredLogger
    tracer: Tracer
    state_engine: StateEngine
    run_count: int = 0

    @classmethod
    def build(cls) -> "GraphOrchestrator":
        logger = StructuredLogger()
        tracer = Tracer()
        state_engine = StateEngine()
        registry = build_default_agent_registry()
        memory_manager = MemoryManager()
        nodes: dict[str, GraphNode] = {
            "input": InputNode(),
            "planner": PlannerNode(planner=build_planning_engine()),
            "agent_dispatch": AgentDispatchNode(registry=registry),
            "execution_sandbox": ExecutionSandboxNode(registry=registry),
            "memory": MemoryNode(memory_manager=memory_manager),
            "reflection": ReflectionNode(),
            "output": OutputNode(),
        }
        definition = GraphDefinition(
            entrypoint="input",
            terminal="output",
            edges={
                "input": "planner",
                "planner": "agent_dispatch",
                "agent_dispatch": "execution_sandbox",
                "execution_sandbox": "memory",
                "memory": "reflection",
                "reflection": "output",
            },
        )
        return cls(
            runner=DeterministicGraphRunner(
                nodes=nodes,
                definition=definition,
                logger=logger,
                tracer=tracer,
                state_engine=state_engine,
            ),
            logger=logger,
            tracer=tracer,
            state_engine=state_engine,
        )

    def run_once(
        self,
        stimulus: str,
        *,
        source: str = "operator",
        context: Mapping[str, Any] | None = None,
    ) -> GraphExecutionResult:
        self.run_count += 1
        normalized = stimulus.strip()
        run_id = self._run_id(normalized, source, self.run_count)
        state = GraphState(
            run_id=run_id,
            stimulus=normalized,
            source=source,
            context=context or {},
        )
        final_state = self.runner.run(state)
        return GraphExecutionResult(state=final_state, global_state=self.state_engine.current)

    def run_loop(
        self,
        stimuli: Iterable[str],
        *,
        source: str = "operator",
        context: Mapping[str, Any] | None = None,
    ) -> tuple[GraphExecutionResult, ...]:
        return tuple(
            self.run_once(stimulus, source=source, context=context)
            for stimulus in stimuli
            if stimulus.strip()
        )

    def debug_run(self, run_id: str) -> GraphDebugReport:
        return self.runner.debug_report(run_id)

    @staticmethod
    def _run_id(stimulus: str, source: str, sequence: int) -> str:
        digest = sha256(f"{sequence}:{source}:{stimulus}".encode("utf-8")).hexdigest()[:12]
        return f"graph_run_{digest}"


def graph_architecture_design() -> dict[str, Any]:
    """Return the no-code architecture map requested by operators."""

    return {
        "style": "LangGraph-inspired deterministic state graph",
        "rules": {
            "self_modification": "forbidden",
            "execution": "sandbox validated only",
            "state_transition": "explicit immutable GraphState replacement",
            "traceability": "each node emits NodeTrace, structured logs, and spans",
            "conditional_flow": "declarative RouteCondition objects only; no runtime callbacks",
        },
        "nodes": [
            {"name": "input", "responsibility": "Normalize stimulus into an intent envelope."},
            {"name": "planner", "responsibility": "Create an ordered task graph; no execution logic."},
            {"name": "agent_dispatch", "responsibility": "Select stateless agents and collect structured outputs."},
            {"name": "execution_sandbox", "responsibility": "Validate task execution requests through sandbox guard."},
            {"name": "memory", "responsibility": "Append episodic and semantic records."},
            {"name": "reflection", "responsibility": "Score the run and explain deterministic quality signals."},
            {"name": "output", "responsibility": "Synthesize final structured response."},
        ],
        "edges": list(zip(GRAPH_NODE_ORDER[:-1], GRAPH_NODE_ORDER[1:], strict=True)),
        "state_contract": {
            "input": "GraphState",
            "output": "GraphState",
            "global_state": "GlobalSystemState",
            "history": "append-only StateVersion records",
            "transitions": "traceable StateTransition records",
            "error_model": "node exceptions become GraphError records and stop the graph",
        },
    }


__all__ = [
    "GRAPH_NODE_ORDER",
    "GraphExecutionResult",
    "GraphOrchestrator",
    "graph_architecture_design",
]
