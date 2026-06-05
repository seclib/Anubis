# ANUBIS Architecture

ANUBIS is a local-first autonomous defense and research system. The production
surface is organized under `core/`; the active bootstrap path now uses a
LangGraph-style deterministic state graph implemented in `core/graph`.

## Graph Architecture

Every major subsystem is represented as a node. Nodes receive an immutable
`GraphState`, return a replacement `GraphState`, and emit a `NodeTrace`.
Execution follows explicit directed edges and stops on structured errors.

Default graph:

1. `input`
2. `planner`
3. `agent_dispatch`
4. `execution_sandbox`
5. `memory`
6. `reflection`
7. `output`

Edges:

```text
input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output
```

## Node Responsibilities

- `input`: normalize operator stimulus into a deterministic intent envelope.
- `planner`: convert intent into an ordered task graph; it contains no execution logic.
- `agent_dispatch`: select stateless agents by task kind and collect structured outputs.
- `execution_sandbox`: validate every task through the sandbox guard; no direct OS execution.
- `memory`: append episodic and semantic records without overwrites.
- `reflection`: score the run using deterministic quality signals.
- `output`: synthesize final structured output with path, traces, memory, and errors.

## Safety Properties

- No self-modifying code is present in the graph runtime.
- Generated code is never executed.
- Sandbox validation is mandatory before any task is marked executed.
- All state transitions are explicit and serializable.
- Node failures become structured `GraphError` records and halt the graph.

## Production Extensions

- `core/swarm` provides native multi-agent coordination with interchangeable agents.
- `core/memory` separates short-term, long-term, and semantic-vector memory layers.
- `core/execution/sandbox_runner.py` is the mandatory execution boundary.
- `core/security/security_kernel.py` centralizes permissions, audit, threat detection, and kill switch state.
- `core/plugins/ecosystem.py` exposes controlled plugin lifecycle and sandboxed execution.
- `ci/auto_refactor.yml` and `.github/workflows/auto-refactor.yml` support review-only refactor proposals without auto-merge or deployment.
