# ANUBIS

ANUBIS is a local-first, deterministic AI orchestration framework built as a
security-first modular monolith. It provides planning, agent dispatch,
sandboxed execution, memory, plugins, observability, CI, Docker deployment, and
an optional graph-based execution mode.

ANUBIS does not modify its own source code, does not execute generated code,
does not enable network access by default, and does not deploy automatically.

## Quick Start

Run locally:

```bash
python3 bootstrap.py
```

Start only the ultra-light core services from Python:

```python
from core.bootstrap import start_ultra_light_bootstrap

runtime = await start_ultra_light_bootstrap()
```

Run with Docker Compose:

```bash
docker compose up --build
```

Run tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 scripts/run_tests.py
```

Run security probes:

```bash
PYTHONPATH=src:. python3 tools/dependency_scanner.py
PYTHONPATH=src:. python3 tools/code_analyzer.py
PYTHONPATH=src:. python3 tools/sandbox_tester.py
python3 tools/hardening_validator.py
```

## Repository Tree

```text
.
├── bootstrap.py
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .dockerignore
├── .github/workflows/
│   ├── lint-pipeline.yml
│   ├── release-approval.yml
│   ├── security-pipeline.yml
│   └── test-pipeline.yml
├── ci/
├── config/
│   ├── agents.yaml
│   ├── audit_policy.yaml
│   ├── logging.yaml
│   ├── permissions.yaml
│   ├── production_hardening.yaml
│   ├── sandbox.yaml
│   ├── secrets_policy.yaml
│   └── settings.yaml
├── core/
│   ├── agents/
│   ├── api/
│   ├── bootstrap/
│   ├── execution/
│   ├── graph/
│   ├── memory/
│   ├── observability/
│   ├── orchestrator/
│   ├── planner/
│   ├── plugins/
│   └── security/
├── docs/
├── scripts/
├── src/anubis/
├── tests/
└── tools/
```

## Core Runtime

The production bootstrap path uses the graph-based orchestrator in `core/graph`.
The default deterministic graph is:

```text
input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output
```

Each node receives an immutable `GraphState` and returns a new `GraphState`.
The state engine records versioned snapshots, transition hashes, changed fields,
node traces, edge decisions, and structured errors.

## Modules

- `core/orchestrator`: production control-plane interfaces and request state.
- `core/planner`: deterministic task graph creation and dependency ordering.
- `core/agents`: stateless planner, analyst, executor, and critic workers.
- `core/execution`: retry, timeout, rollback, and execution result handling.
- `core/security`: deny-by-default permissions, sandbox guard, audit log, kill switch.
- `core/memory`: append-only episodic memory, semantic records, vector abstraction.
- `core/plugins`: declarative plugin interface, registry, loader, and sandbox boundary.
- `core/swarm`: swarm-native multi-agent coordination with interchangeable agents.
- `core/observability`: JSON logging, tracing, metrics, and dashboard feed.
- `core/graph`: optional graph runtime with conditional deterministic routing.
- `core/bootstrap`: startup composition used by `bootstrap.py`.
- `core/bootstrap/ultra_light.py`: minimum startup path for event bus, memory, and orchestrator only.

## Production Pillars

1. Swarm-native coordination
   - `core/swarm` coordinates planner, analyst, executor, and critic agents.
   - Agents are selected from an interchangeable `AgentPool`.
   - Consensus is deterministic and confidence-weighted.

2. Memory-first system
   - `ShortTermMemory` is bounded and volatile.
   - `LongTermMemory` stores append-only episodic and semantic records.
   - `SemanticVectorStore` owns local deterministic vector retrieval.
   - `MemorySystem` exposes these as strongly separated layers.

3. Execution sandbox
   - All graph task execution passes through `core/execution/sandbox_runner.py`.
   - Executor agents prepare sandbox requests only.
   - Direct execution remains forbidden.

4. Security-by-design
   - `SecurityKernel` centralizes permission checks, audit logging, sandbox validation,
     threat detection, and the global kill switch.
   - Policies remain deny-by-default.

5. Plugin ecosystem
   - `PluginEcosystem` provides a controlled OS-like extension surface.
   - Plugins are declarative, registry-managed, lifecycle-controlled, and sandboxed.

6. Self-evolving CI/CD, safely constrained
   - `ci/auto_refactor.yml` and `.github/workflows/auto-refactor.yml` generate
     review-only refactor proposals.
   - No auto-commit, auto-push, auto-merge, or deployment is allowed.

## Security Model

ANUBIS enforces:

- no self-modifying code
- no unrestricted OS execution
- no generated-code execution
- no network access by default
- sandbox-only execution boundaries
- deny-by-default permissions
- append-only audit records
- no production auto-deployment
- manual approval gate for releases
- auto-refactor workflows are proposal-only and review-only

Production hardening policies live in:

- `config/production_hardening.yaml`
- `config/permissions.yaml`
- `config/sandbox.yaml`
- `config/secrets_policy.yaml`
- `config/audit_policy.yaml`

Detailed docs are in `docs/security_model.md`,
`docs/execution_sandbox.md`, `docs/production_hardening.md`, and
`docs/docker_runtime_security.md`.

## Docker

The Docker runtime uses:

- pinned Python slim image
- non-root UID/GID `10001:10001`
- read-only root filesystem
- dropped Linux capabilities
- `no-new-privileges`
- PID, CPU, memory, and file descriptor limits
- no network by default via `network_mode: none`
- tmpfs-only writable `/tmp`

Use the network-enabled profile only for explicitly reviewed integrations:

```bash
docker compose --profile network-enabled up anubis-network-enabled
```

## CI/CD

GitHub Actions workflows cover:

- compile checks
- deterministic unit and integration tests
- sandbox execution tests
- Docker Compose validation
- hardened container smoke test
- static architecture scan
- dependency scan
- hardening policy validation
- lint checks
- manual release approval

There is no automatic production deployment workflow.

## Graph Debugging

Graph results include:

- `execution_path`
- `traces`
- `state_history`
- `state_transitions`
- `errors`

Programmatic debugging is available through:

```python
from core.graph import GraphOrchestrator

orchestrator = GraphOrchestrator.build()
result = orchestrator.run_once("Investigate local anomaly")
debug = orchestrator.debug_run(result.state.run_id)
```

## Development Notes

The runtime has no required third-party dependencies. Development tools such as
pytest and Ruff are optional and declared in `pyproject.toml`.

The custom test runner is intentionally standard-library based so CI and local
validation can run in minimal environments.
