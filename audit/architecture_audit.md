# ANUBIS Architecture Audit

Audit date: 2026-06-05

## Executive Summary

ANUBIS is a local-first Python orchestration framework implemented as a modular monolith. The active CLI and Docker entrypoint is `bootstrap.py`, which delegates to `core.bootstrap.main()` and runs the deterministic state graph in `core/graph`.

The repository contains two major runtime layers:

- `core/`: current production-oriented graph runtime, sandbox boundary, security kernel, memory, plugins, swarm, planner, and observability.
- `src/anubis/`: richer legacy or experimental runtime with a "living loop", agents, memory, retrieval, safety monitoring, plugins, audit, evolution, lifecycle, and research swarm systems.

This split is the most important architectural fact in the repository. It gives the project broad coverage, but it also creates duplicated concepts and unclear ownership between `core.*` and `anubis.*`.

## Repository Structure

Top-level inventory:

- `bootstrap.py`: thin entrypoint that adds `src` to `sys.path` and calls `core.bootstrap.main`.
- `core/`: production control plane and deterministic graph runtime.
- `src/anubis/`: package implementation for the living-loop runtime and many foundational abstractions.
- `agents/`: research agent implementations used by `src/anubis/life_cycle/boot_sequence.py`.
- `config/`: YAML policies for agents, logging, sandboxing, permissions, audits, secrets, and hardening.
- `docs/`: architecture, security, sandbox, Docker, memory, production hardening, and agent notes.
- `tests/`: broad deterministic test suite.
- `tools/`: standard-library validation tools.
- `scripts/`: local run and custom test runner scripts.
- `.github/workflows/` and `ci/`: CI workflows and matching declarative pipeline summaries.
- `Dockerfile` and `docker-compose.yml`: hardened local container runtime.

Observed file counts:

- Python files: 204 total, 18,831 total Python lines.
- Source files under `core` and `src`: 159 Python files.
- Largest modules by line count: `src/anubis/swarm.py` at 609 lines, `src/anubis/memory.py` at 600 lines, `src/anubis/plugins.py` at 499 lines.

## Active Runtime Path

The active bootstrap path is:

```text
bootstrap.py
  -> core.bootstrap.main
  -> core.bootstrap.async_main
  -> core.bootstrap.run_bootstrap
  -> core.graph.GraphOrchestrator.build()
  -> DeterministicGraphRunner
```

Default graph:

```text
input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output
```

Node responsibilities:

- `InputNode`: validates non-empty stimulus and normalizes intent.
- `PlannerNode`: builds deterministic ordered task graph.
- `AgentDispatchNode`: maps task kind to stateless agent role and collects structured outputs.
- `ExecutionSandboxNode`: routes each task through `SandboxRunner`.
- `MemoryNode`: appends episodic and semantic records through `MemoryManager`.
- `ReflectionNode`: computes deterministic run quality metrics.
- `OutputNode`: creates final structured output.

State model:

- Graph state is immutable by replacement.
- `StateEngine` stores state history and transitions.
- `GraphExecutionResult.to_dict()` exposes execution path, traces, transitions, errors, plan data, output, and architecture metadata.

## Secondary Runtime Path

`core/orchestrator/orchestrator.py` exposes a production control plane that builds `anubis.life_cycle.boot_sequence.build_runtime()`. That runtime composes:

- `InMemoryEventBus`
- `ConsciousnessLogger`
- living agents: watcher, thinker, executor, healer, predator
- `PermissionSystem` and default sandbox
- async `anubis.orchestrator.Orchestrator`
- `ExecutionLayer` with retry and timeout policy
- episodic and semantic memory
- research `HiveMind`
- optional `EvolutionEngine`
- `PrincipalLoop`

The secondary runtime is exercised by tests and remains important, but it is not the default CLI/Docker entrypoint.

## Architecture Components

### Planning

- `core/planner`: deterministic planning engine, task graph, dependency resolver, validator.
- `src/anubis/planner.py`: richer async planning engine for the living-loop runtime.

### Agents

- `core/agents`: stateless planner, analyst, executor, critic workers behind `AgentRegistry`.
- `src/anubis/agents.py`: async registry with capacity tracking and task assignment.
- `src/anubis/agents_life`: watcher, thinker, executor, healer, predator living agents.
- `agents/`: research agents used by the research hive.

### Execution

- `core/execution/sandbox_runner.py`: current graph sandbox boundary. It selects the executor agent, gathers a structured executor result, then validates through `SandboxGuard`.
- `src/anubis/execution.py`: async execution layer with retry, timeout, rollback, event publication, and sandbox authorization.

Current execution is intentionally simulation-oriented. The audited graph path does not spawn processes or execute generated code.

### Security

- `core/security`: permission engine, sandbox guard, audit logger, kill switch, threat detector, security kernel.
- `src/anubis/sandbox.py` and `src/anubis/safety.py`: capability sandbox and event-driven safety monitor.

### Memory and RAG

- `core/memory`: append-only episodic and semantic memory plus deterministic vector retrieval.
- `src/anubis/memory.py`: scoped shared memory, storage policy, sensitivity controls, conflict handling, vector sync.
- `src/anubis/retrieval.py`: query routing over scoped/global vector DB adapters.

Retrieval uses local deterministic hashing embeddings, not model-based embeddings.

### Plugins

- `core/plugins`: manifest loader, registry, manager, lifecycle, sandboxed execution.
- `src/anubis/plugins.py`: richer async plugin lifecycle and dependency system.

Plugin manifests are declarative; dynamic code import is intentionally avoided in the `core` loader.

### Observability

- `core/observability`: structured logger, tracer, metrics, dashboard feed.
- `src/anubis/observability`: behavior traces, consciousness logger, system vitals, introspection dashboard.

### API

- `core/api`: minimal local API facade. There is no FastAPI, uvicorn, or external HTTP server dependency.
- `src/anubis/api_body`: request/response body models for internal runtime boundaries.

## Tauri and Frontend Status

No Tauri project is present. The audit found no `package.json`, `Cargo.toml`, `tauri.conf.*`, Vite config, Node lockfile, or frontend build system. ANUBIS is currently a Python CLI/container runtime, not a Tauri desktop app.

## Architectural Strengths

- Active runtime has a clear deterministic graph.
- Security boundaries are documented and tested.
- Runtime dependency surface is intentionally minimal.
- Docker configuration is hardened by default.
- Tests cover graph runtime, memory, retrieval, security, plugins, execution, swarm, audit, evolution, and bootstrap behavior.
- CI is review-only for auto-refactor and avoids production deployment.

## Architectural Weaknesses

- `core` and `src/anubis` duplicate many concepts: agents, orchestrators, memory, retrieval, execution, plugins, sandbox, safety.
- README mentions several modules as if all are top-level production modules, but actual active entrypoint is narrower.
- Tracked `__pycache__` files exist throughout the repository, which pollutes git state during verification.
- The default graph sandbox validates but does not perform real process isolation; Docker provides runtime isolation, but in-process tasks remain simulation-oriented.
- No durable persistence layer exists for memory, audit records, events, metrics, or state history.

## Architecture Conclusion

ANUBIS is best described as a deterministic, security-first Python orchestration prototype with a strong local-first posture and unusually broad test coverage. The primary architectural decision needed next is not a feature addition; it is ownership clarification between `core` and `src/anubis` so the project has one canonical runtime model.
