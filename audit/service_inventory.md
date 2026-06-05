# ANUBIS Service Inventory

Audit date: 2026-06-05

## Service Model

ANUBIS currently runs as a single Python process. There are no separate database, queue, vector database, API server, worker, frontend, Tauri, or model-serving services in the repository.

Primary service surfaces:

- Local CLI process via `python3 bootstrap.py`.
- Hardened container service via Docker Compose.
- Optional network-enabled container profile for explicitly reviewed future integrations.
- In-process event, memory, graph, agent, plugin, and security services.

## Entrypoints

### CLI

Command:

```bash
python3 bootstrap.py
```

Behavior:

- Adds `src` to `sys.path`.
- Calls `core.bootstrap.main()`.
- Runs the `core.graph.GraphOrchestrator` path.
- Prints structured JSON.

### Docker Compose

Default command:

```bash
docker compose up --build
```

Default service:

- Name: `anubis`
- Network: disabled with `network_mode: none`
- Command: `["Investigate local authentication anomaly", "--source", "docker"]`

Network-enabled service:

- Name: `anubis-network-enabled`
- Profile: `network-enabled`
- Environment marks `ANUBIS_NETWORK=explicit`
- Does not itself grant application-level network permission.

### Scripts

- `scripts/run_dev.sh`: runs bootstrap with `PYTHONPATH` including `src`.
- `scripts/run_prod.sh`: runs bootstrap with `ANUBIS_ENV=production`.
- `scripts/run_tests.py`: custom standard-library test runner.
- `scripts/run_tests.sh`: shell wrapper for tests.
- `scripts/seed_memory.py`: memory seeding utility.

## In-Process Service Inventory

### Graph Runtime

- Location: `core/graph`
- Type: deterministic state graph
- Entrypoint: `GraphOrchestrator.build()`
- Nodes: input, planner, agent dispatch, execution sandbox, memory, reflection, output
- Persistence: in-memory only

### Orchestrator Services

- `core/orchestrator`: production control-plane wrapper over the living runtime.
- `src/anubis/orchestrator.py`: async task orchestration, agent registry integration, execution dispatch.
- Persistence: in-memory request and task state.

### Agent Services

- `core/agents`: stateless structured agents used by graph runtime.
- `src/anubis/agents_life`: living runtime agents.
- `agents/`: research agents.
- Capacity/state: in-memory.

### Execution Services

- `core/execution/sandbox_runner.py`: graph execution boundary, validates tasks via sandbox guard.
- `src/anubis/execution.py`: async execution layer with retries, timeouts, rollback, and event publication.
- External process execution: not present in active path.

### Memory Services

- `core/memory/MemoryManager`: append-only episodic and semantic memory with vector index.
- `core/memory/MemorySystem`: separated short-term, long-term, and semantic vector memory.
- `src/anubis/memory.SharedMemory`: scoped memory with isolation, storage policy, conflict strategy, and vector sync.
- Persistence: in-memory only.

### RAG and Retrieval Services

- `core/memory/retriever.py`: namespace-filtered memory retrieval.
- `core/memory/vector_store.py`: append-only in-memory vector store.
- `src/anubis/retrieval.py`: scoped/global query router over `SharedMemoryVectorDB`.
- Embeddings: deterministic local token hashing, 64 dimensions by default.
- External vector DB: none.

### Security Services

- `core/security/PermissionEngine`
- `core/security/SandboxGuard`
- `core/security/AuditLogger`
- `core/security/KillSwitch`
- `core/security/ThreatDetector`
- `core/security/SecurityKernel`
- `src/anubis/sandbox.PermissionSystem`
- `src/anubis/safety.SafetyMonitor`

Persistence: in-memory audit records and safety state.

### Plugin Services

- `core/plugins/PluginEcosystem`
- `core/plugins/PluginLoader`
- `core/plugins/PluginManager`
- `src/anubis/plugins.py`

Plugin loading:

- `core` loader reads JSON manifests only.
- Plugin execution requires registration, started lifecycle state, permissions, and sandbox approval.

### Swarm Services

- `core/swarm/SwarmCoordinator`: deterministic planner -> analyst -> executor -> critic loop.
- `src/anubis/swarm.SwarmCoordinator`: role assignment, consensus, performance scoring, dynamic replacement.
- `src/anubis/core_life/swarm.HiveMind`: research swarm with role allocation, consensus, shared memory.

### Observability Services

- `core/observability/StructuredLogger`
- `core/observability/Tracer`
- `core/observability/MetricsCollector`
- `core/observability/DashboardFeed`
- `src/anubis/observability/*`

Persistence: in-memory logs, traces, metrics.

### API Service

- `core/api`: minimal facade for embedding ANUBIS in local services.
- No HTTP listener or web server dependency is present.

## CI Services

GitHub Actions workflows:

- `test-pipeline.yml`: compile, custom tests, bootstrap integration, Docker config, Docker build, container smoke test, sandbox tests.
- `security-pipeline.yml`: dependency scan, static architecture scan, sandbox probe, hardening validator, forbidden deployment command guard, Docker hardening validation, CodeQL.
- `lint-pipeline.yml`: compile, Ruff critical lint checks, text formatting guard.
- `auto-refactor.yml`: review-only proposal artifact; no source edits, pushes, merges, or deployment.
- `release-approval.yml`: manual release validation gate; no deployment.

Declarative CI summaries also exist under `ci/`.

## Missing or Nonexistent Services

- No Tauri desktop service.
- No web frontend.
- No external API server.
- No database.
- No Redis or queue.
- No external vector database.
- No LLM provider integration.
- No production deployment service.
- No networked runtime in the default profile.

## Service Inventory Conclusion

ANUBIS is a single-process, in-memory orchestration runtime with strong internal service boundaries but no distributed service topology. The project is operationally simple today; the biggest service risk is that many service-like abstractions imply production capabilities that are not durable, networked, or externally integrated yet.
