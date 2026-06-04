# Target Architecture

Date: 2026-06-04

Purpose: define the ideal production-grade architecture for Anubis after consolidating the duplicated root, `backend/`, `anubis/`, CLI, API, RAG, tool, and UI implementations.

This document describes the target state, not the current state. It intentionally chooses one canonical architecture so future work has one obvious home.

## Architectural Principles

1. Single canonical Python package: all product Python code lives under `anubis/`.
2. Clean dependency direction: interfaces call application services; application services depend on domain and ports; infrastructure implements ports.
3. One implementation per capability: one agent loop, one tool pipeline, one memory/RAG pipeline, one API adapter, one CLI adapter, one desktop app.
4. Multi-model by design: model providers are adapters behind a common model-router port.
5. AI-agent friendly: stable module boundaries, explicit contracts, clear names, small files, typed request/result objects, and commandable service APIs.
6. Security centralization: all filesystem, shell, git, network, and tool execution flows pass through one policy and audit layer.
7. Testability first: domain and application logic run without FastAPI, Tauri, Qdrant, Ollama, Redis, or subprocess access.
8. Deployment clarity: API, worker, CLI, and desktop compose the same application services through one dependency container.
9. No hidden runtime state in source folders: generated files, local state, logs, virtualenvs, build artifacts, and dependency folders are outside versioned source.
10. Delete legacy after migration: compatibility shims are temporary and must have owners, removal criteria, and tests.

## Complete Folder Tree

```text
.
├── anubis/
│   ├── __init__.py
│   ├── py.typed
│   ├── bootstrap/
│   │   ├── __init__.py
│   │   ├── container.py
│   │   ├── lifecycle.py
│   │   └── settings.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── roles.py
│   │   │   └── policies.py
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── scoring.py
│   │   │   └── policies.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── permissions.py
│   │   │   └── policy.py
│   │   ├── workspace/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── paths.py
│   │   ├── skills/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── validation.py
│   │   ├── orchestration/
│   │   │   ├── __init__.py
│   │   │   ├── events.py
│   │   │   ├── state.py
│   │   │   └── tasks.py
│   │   └── security/
│   │       ├── __init__.py
│   │       ├── models.py
│   │       ├── trust.py
│   │       └── redaction.py
│   ├── application/
│   │   ├── __init__.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── loop.py
│   │   │   ├── planner.py
│   │   │   ├── executor.py
│   │   │   ├── critic.py
│   │   │   ├── verifier.py
│   │   │   ├── session_service.py
│   │   │   └── prompt_service.py
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── ingestion_service.py
│   │   │   ├── retrieval_service.py
│   │   │   ├── context_service.py
│   │   │   ├── compression_service.py
│   │   │   └── cache_service.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── tool_service.py
│   │   │   ├── registry_service.py
│   │   │   ├── policy_service.py
│   │   │   └── audit_service.py
│   │   ├── workspace/
│   │   │   ├── __init__.py
│   │   │   ├── file_service.py
│   │   │   ├── git_service.py
│   │   │   └── vault_service.py
│   │   ├── skills/
│   │   │   ├── __init__.py
│   │   │   ├── skill_service.py
│   │   │   ├── plugin_service.py
│   │   │   └── dsl_service.py
│   │   ├── orchestration/
│   │   │   ├── __init__.py
│   │   │   ├── task_service.py
│   │   │   ├── event_service.py
│   │   │   ├── scheduler_service.py
│   │   │   └── worker_service.py
│   │   └── health/
│   │       ├── __init__.py
│   │       └── health_service.py
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── clock.py
│   │   ├── event_bus.py
│   │   ├── file_store.py
│   │   ├── git.py
│   │   ├── llm.py
│   │   ├── embeddings.py
│   │   ├── vector_store.py
│   │   ├── keyword_index.py
│   │   ├── cache.py
│   │   ├── process.py
│   │   ├── audit_log.py
│   │   ├── secret_store.py
│   │   └── watcher.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   ├── ollama.py
│   │   │   ├── openai.py
│   │   │   ├── anthropic.py
│   │   │   └── local_stub.py
│   │   ├── embeddings/
│   │   │   ├── __init__.py
│   │   │   ├── ollama.py
│   │   │   ├── sentence_transformers.py
│   │   │   └── deterministic.py
│   │   ├── vector_store/
│   │   │   ├── __init__.py
│   │   │   ├── qdrant.py
│   │   │   └── in_memory.py
│   │   ├── keyword_index/
│   │   │   ├── __init__.py
│   │   │   └── local.py
│   │   ├── cache/
│   │   │   ├── __init__.py
│   │   │   ├── redis.py
│   │   │   └── memory.py
│   │   ├── filesystem/
│   │   │   ├── __init__.py
│   │   │   ├── local_file_store.py
│   │   │   ├── vault_store.py
│   │   │   └── watcher.py
│   │   ├── process/
│   │   │   ├── __init__.py
│   │   │   ├── sandbox.py
│   │   │   └── subprocess_runner.py
│   │   ├── git/
│   │   │   ├── __init__.py
│   │   │   └── cli_git.py
│   │   ├── audit/
│   │   │   ├── __init__.py
│   │   │   ├── jsonl.py
│   │   │   └── structured_logger.py
│   │   └── secrets/
│   │       ├── __init__.py
│   │       └── environment.py
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── app.py
│   │   │   ├── dependencies.py
│   │   │   ├── schemas.py
│   │   │   ├── errors.py
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       ├── agents.py
│   │   │       ├── chat.py
│   │   │       ├── memory.py
│   │   │       ├── tools.py
│   │   │       ├── workspace.py
│   │   │       ├── skills.py
│   │   │       ├── health.py
│   │   │       └── openai_compat.py
│   │   ├── cli/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── commands.py
│   │   │   ├── renderer.py
│   │   │   └── session.py
│   │   ├── worker/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   └── jobs.py
│   │   └── desktop_bridge/
│   │       ├── __init__.py
│   │       ├── commands.py
│   │       └── schemas.py
│   └── shared/
│       ├── __init__.py
│       ├── errors.py
│       ├── json.py
│       ├── logging.py
│       ├── text.py
│       └── typing.py
├── apps/
│   └── desktop/
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── src/
│       │   ├── main.tsx
│       │   ├── app/
│       │   │   ├── App.tsx
│       │   │   ├── layout/
│       │   │   ├── state/
│       │   │   ├── api/
│       │   │   ├── components/
│       │   │   └── views/
│       │   └── styles/
│       └── src-tauri/
│           ├── Cargo.toml
│           ├── tauri.conf.json
│           └── src/
│               ├── main.rs
│               ├── lib.rs
│               └── commands.rs
├── plugins/
│   ├── README.md
│   └── examples/
│       └── vault-memory/
├── skills/
│   ├── README.md
│   └── builtins/
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── shared/
│   ├── integration/
│   │   ├── api/
│   │   ├── infrastructure/
│   │   └── desktop_bridge/
│   ├── contract/
│   │   ├── ports/
│   │   └── openai_compat/
│   ├── e2e/
│   └── fixtures/
├── docs/
│   ├── architecture/
│   │   ├── README.md
│   │   ├── adr/
│   │   ├── dependency-rules.md
│   │   └── module-map.md
│   ├── onboarding/
│   ├── operations/
│   └── api/
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.worker
│   │   └── docker-compose.dev.yml
│   ├── k8s/
│   ├── systemd/
│   └── scripts/
├── scripts/
│   ├── dev_api.sh
│   ├── dev_desktop.sh
│   ├── test.sh
│   ├── lint.sh
│   └── migrate_legacy.sh
├── pyproject.toml
├── package.json
├── README.md
├── CHANGELOG.md
└── .env.example
```

## Folder Responsibilities

### `anubis/`

Canonical Python package. All importable production Python code lives here. No root-level product packages remain after migration.

### `anubis/bootstrap/`

Composition root and runtime configuration.

- `settings.py`: typed Pydantic settings for API, models, embeddings, vector stores, vault paths, tools, security, and deployment.
- `container.py`: builds the dependency graph for API, CLI, workers, and tests.
- `lifecycle.py`: startup/shutdown hooks for watchers, vector stores, background jobs, and cleanup.

Only `interfaces/*` entrypoints should construct the container.

### `anubis/domain/`

Pure business model and policy layer. No framework imports. No network, disk, subprocess, FastAPI, Tauri, Qdrant, Redis, Ollama, or environment-variable reads.

Domain modules contain:

- Dataclasses/Pydantic-neutral models.
- Enums and value objects.
- Domain validation rules.
- Security, permission, scoring, and task-state rules.

### `anubis/application/`

Use-case orchestration layer. This is where product behavior lives.

Application services depend on:

- `anubis.domain`
- `anubis.ports`
- `anubis.shared`

Application services must not import concrete infrastructure adapters, FastAPI, Tauri, or CLI rendering code.

### `anubis/ports/`

Protocol definitions for external capabilities.

Ports define what the application needs:

- LLM generation and streaming.
- Embeddings.
- Vector search.
- Keyword search.
- File and vault storage.
- Git.
- Process execution.
- Cache.
- Audit logging.
- Event bus.
- Secret access.
- Filesystem watchers.

Ports use typed request/result objects from domain modules or define minimal protocol DTOs.

### `anubis/infrastructure/`

Concrete adapters for external systems.

Infrastructure implements ports and owns integration details:

- Qdrant client behavior.
- Ollama/OpenAI/Anthropic calls.
- Redis cache.
- Local filesystem.
- Subprocess execution.
- Git CLI.
- JSONL audit logs.
- Watchdog-based watchers.

Infrastructure may import external libraries and settings. It must not import `anubis.interfaces`.

### `anubis/interfaces/`

Human, machine, and process entrypoints.

- `api/`: FastAPI app and HTTP route adapters.
- `cli/`: terminal adapter.
- `worker/`: background worker adapter.
- `desktop_bridge/`: schemas and command handlers used by Tauri.

Interfaces translate external requests into application service calls. They do not contain business logic.

### `anubis/shared/`

Small cross-cutting utilities that are truly generic:

- Structured errors.
- JSON serialization.
- Logging helpers.
- Text normalization.
- Common typing helpers.

This folder must remain small. It is not a dumping ground.

### `apps/desktop/`

The single production desktop UI. Uses Vite/React/Tauri unless a future ADR replaces it.

Responsibilities:

- UI layout, views, client-side state, and visual components.
- Typed API/Tauri client wrappers.
- No direct LLM orchestration.
- No independent memory/RAG implementation except UI cache.

### `plugins/`

External plugin examples and packaged plugin assets. Runtime plugin loading is implemented in `anubis/application/skills` and infrastructure adapters.

### `skills/`

Built-in skill definitions and documentation. Skill parsing, validation, and execution live in `anubis/application/skills`.

### `tests/`

Test suite organized by architectural layer:

- `unit/`: pure domain/application tests.
- `integration/`: adapters with real or containerized dependencies.
- `contract/`: port compliance and API compatibility.
- `e2e/`: full API/CLI/desktop flows.
- `fixtures/`: deterministic test vaults, repos, model outputs, and tool results.

### `docs/`

Design, operations, onboarding, API reference, and ADRs. Architecture changes require an ADR.

### `infra/`

Deployment assets only. No application source code.

### `scripts/`

Developer and CI scripts. Scripts should call package entrypoints, not reimplement product logic.

## Service Responsibilities

### Agent Services

`anubis/application/agents/loop.py`

- Owns the canonical agent lifecycle.
- Coordinates planning, context retrieval, model calls, tool execution, critique, verification, retry, and final response assembly.
- Emits domain events for observability.

`planner.py`

- Converts a user/task request plus retrieved context into a typed plan.
- Uses model router through `LLMPort` only when needed.
- Applies deterministic fallback plans for testability.

`executor.py`

- Executes plan steps through `ToolService`.
- Never invokes subprocesses or filesystem directly.
- Produces typed step results.

`critic.py`

- Evaluates answer grounding, hallucination risk, source coverage, and retry need.
- Uses retrieved evidence and structured result objects.

`verifier.py`

- Verifies tool results and task completion.
- Contains file/command/result validation rules currently duplicated across backend implementations.

`session_service.py`

- Owns chat/session history, run IDs, resumability, cancellation, and event streaming metadata.

`prompt_service.py`

- Central prompt registry for planner, executor, critic, reviewer, and model-specific formatting.
- Replaces duplicated `prompts.py` files.

### Memory And RAG Services

`ingestion_service.py`

- Ingests vault files, code files, documents, and skills.
- Calls chunker, embedder, vector store, keyword index, and metadata persistence through ports.

`retrieval_service.py`

- Performs vector, keyword, metadata, and recency retrieval.
- Combines ranking and filtering policies from `domain/memory`.

`context_service.py`

- Builds the final context packet for agent runs.
- Enforces token budgets, trust scores, source attribution, and source diversity.

`compression_service.py`

- Compresses long memory/session histories.
- Produces durable summaries with provenance.

`cache_service.py`

- Owns query cache and short-lived retrieval cache behavior.
- Uses `CachePort`.

### Tool Services

`tool_service.py`

- Single execution gateway for all tools.
- Validates request, permissions, sandbox rules, execution timeout, output limits, and audit logging.

`registry_service.py`

- Registers built-in tools and plugin-provided tools.
- Provides discovery metadata to API/CLI/desktop.

`policy_service.py`

- Applies command allowlists, forbidden commands, path containment, network access rules, write permissions, and per-session approvals.

`audit_service.py`

- Records tool requests, decisions, execution results, errors, and durations.
- Uses `AuditLogPort`.

### Workspace Services

`file_service.py`

- Safe read/write/list/search operations within workspace boundaries.

`git_service.py`

- Status, diff, branch, commit, and PR preparation through `GitPort`.

`vault_service.py`

- Reads/writes vault notes, resolves note paths, normalizes Markdown metadata, and emits watcher events.

### Skill And Plugin Services

`skill_service.py`

- Loads built-in and vault skills.
- Matches triggers to tasks.
- Provides skill context to the agent loop.

`plugin_service.py`

- Discovers, validates, enables, disables, and audits plugins.
- Controls plugin capability permissions.

`dsl_service.py`

- Parses and validates DSL/plugin manifests if the DSL remains part of the product.

### Orchestration Services

`task_service.py`

- Creates, updates, cancels, resumes, and snapshots tasks.

`event_service.py`

- Publishes and subscribes to domain/application events.
- Provides one event model for API streaming, UI bridge, workers, and logs.

`scheduler_service.py`

- Schedules recurring ingestion, maintenance, and cleanup jobs.

`worker_service.py`

- Runs background jobs using the same application services as API/CLI.

### Health Service

`health_service.py`

- Reports liveness, readiness, dependency health, model availability, vector-store availability, and degraded-mode status.

## Module Responsibilities

### Domain Modules

`domain/agents/models.py`

- `AgentRun`, `AgentRequest`, `AgentResponse`, `Plan`, `PlanStep`, `StepResult`, `Critique`, `Verification`.

`domain/agents/roles.py`

- Role definitions: planner, executor, critic, reviewer, verifier, researcher.
- No prompts with infrastructure details.

`domain/agents/policies.py`

- Retry limits, grounding thresholds, citation requirements, max tool calls, and safe fallback rules.

`domain/memory/models.py`

- `MemoryItem`, `Chunk`, `Source`, `RetrievalQuery`, `RetrievalResult`, `ContextPacket`.

`domain/memory/scoring.py`

- Deterministic scoring helpers: recency, confidence, source trust, lexical overlap, deduplication.

`domain/memory/policies.py`

- Context budget, minimum trust, source inclusion/exclusion, summarization thresholds.

`domain/tools/models.py`

- `ToolDefinition`, `ToolRequest`, `ToolResult`, `ToolExecutionContext`, `ToolPermission`.

`domain/tools/permissions.py`

- Permission enums and capability checks.

`domain/tools/policy.py`

- Pure validation rules for command categories, write scope, network scope, and audit requirements.

`domain/workspace/models.py`

- `Workspace`, `VaultNote`, `GitChange`, `FileMatch`, `PathRef`.

`domain/workspace/paths.py`

- Pure path normalization and containment decisions.

`domain/skills/models.py`

- `Skill`, `SkillTrigger`, `SkillManifest`, `PluginManifest`, `SkillExecution`.

`domain/skills/validation.py`

- Manifest and skill validation rules.

`domain/orchestration/events.py`

- Canonical event schema for task, agent, tool, memory, skill, and system events.

`domain/orchestration/state.py`

- Task and run state machine definitions.

`domain/security/*`

- Trust score models, sanitization decisions, redaction policies, and safety classifications.

### Port Modules

`ports/llm.py`

- `LLMPort`, `ModelRouterPort`, streaming chunk types, model capabilities, token accounting.

`ports/embeddings.py`

- `EmbeddingPort`, embedding request/result types.

`ports/vector_store.py`

- Collection management, upsert, delete, search, health.

`ports/file_store.py`

- Safe abstract file/vault operations.

`ports/process.py`

- Process execution request/result interface. No policy logic here.

`ports/git.py`

- Git status/diff/commit/branch/log operations.

`ports/cache.py`

- Get/set/delete/health with TTL.

`ports/audit_log.py`

- Append-only audit event sink.

`ports/event_bus.py`

- Publish/subscribe event abstraction.

### Infrastructure Modules

`infrastructure/llm/router.py`

- Selects provider/model based on task type, availability, cost, context window, and settings.

`infrastructure/llm/ollama.py`

- Ollama chat/generate/stream adapter.

`infrastructure/llm/openai.py`

- OpenAI-compatible adapter.

`infrastructure/llm/anthropic.py`

- Anthropic-compatible adapter if enabled.

`infrastructure/vector_store/qdrant.py`

- Single Qdrant adapter. Replaces all duplicate Qdrant stores.

`infrastructure/process/sandbox.py`

- Concrete sandboxed command executor. Uses application policy decisions and domain tool models.

`infrastructure/filesystem/local_file_store.py`

- Local file implementation for `FileStorePort`.

`infrastructure/filesystem/vault_store.py`

- Obsidian/vault-specific file adapter.

`infrastructure/audit/jsonl.py`

- JSONL audit sink for local development and desktop.

### Interface Modules

`interfaces/api/app.py`

- FastAPI app factory.
- Adds middleware, exception handlers, routers, lifecycle hooks.

`interfaces/api/dependencies.py`

- Injects application services from the container.
- Replaces route-local `get_indexer`, `get_retriever`, `get_agent`, and `reset_route_state`.

`interfaces/api/schemas.py`

- HTTP request/response schemas only.
- Maps to/from domain/application models.

`interfaces/api/routes/openai_compat.py`

- `/v1/models`, `/v1/chat/completions`, streaming responses, OpenAI-compatible payloads.

`interfaces/api/routes/agents.py`

- Agent run, stream, cancel, resume, session endpoints.

`interfaces/api/routes/memory.py`

- Ingest, retrieve, query, sync, and source endpoints.

`interfaces/api/routes/tools.py`

- Tool discovery and invocation endpoints.

`interfaces/api/routes/workspace.py`

- File, git, vault, and project workspace endpoints.

`interfaces/cli/main.py`

- Console entrypoint exposed by `pyproject.toml`.

`interfaces/cli/commands.py`

- CLI command definitions mapped to application service calls.

`interfaces/cli/renderer.py`

- Terminal output only. No business logic.

`interfaces/worker/jobs.py`

- Background job definitions calling application services.

`interfaces/desktop_bridge/commands.py`

- Thin local bridge for Tauri commands when direct HTTP is not appropriate.

## Dependency Rules

### Allowed Dependencies

```text
interfaces -> bootstrap -> application -> domain
interfaces -> bootstrap -> infrastructure -> ports
application -> domain
application -> ports
application -> shared
infrastructure -> ports
infrastructure -> domain
infrastructure -> shared
domain -> shared typing/errors only, if necessary
```

### Forbidden Dependencies

- `domain` must not import `application`, `ports`, `infrastructure`, or `interfaces`.
- `application` must not import `infrastructure` or `interfaces`.
- `ports` must not import `infrastructure` or `interfaces`.
- `infrastructure` must not import `interfaces`.
- API routes must not construct concrete services directly.
- CLI commands must not call infrastructure adapters directly.
- Desktop/Tauri commands must not call model providers or subprocesses directly.
- Tests must not import legacy modules after migration.

### Boundary Rules

- All model calls go through `LLMPort` or `ModelRouterPort`.
- All embedding calls go through `EmbeddingPort`.
- All vector operations go through `VectorStorePort`.
- All file/vault operations go through `FileStorePort` or `VaultService`.
- All shell/process operations go through `ToolService`.
- All tool execution decisions are audited.
- All route dependencies come from `interfaces/api/dependencies.py`.
- All configuration comes from `bootstrap/settings.py`.

## Multi-Model Architecture

The model layer is built around a router, not hard-coded providers.

```text
AgentLoop
  -> PromptService
  -> ModelRouterPort
  -> LLM provider adapter
```

Model router responsibilities:

- Choose model by task class: planning, coding, critique, summarization, retrieval synthesis, chat.
- Respect model capabilities: context window, tool support, JSON reliability, streaming, local/remote availability.
- Provide fallback chains.
- Track model health.
- Normalize streaming chunks.
- Normalize errors and rate limits.

Provider adapters:

- `ollama.py`: local models.
- `openai.py`: OpenAI-compatible APIs.
- `anthropic.py`: Anthropic APIs.
- `local_stub.py`: deterministic tests.

No application service should know whether a model is Ollama, OpenAI, Anthropic, or a test stub.

## Agent-Friendly Design Rules

For human and AI maintainers:

- One module has one reason to change.
- Every service has a typed request and typed result.
- Every external side effect is behind a port.
- Every folder has a README once implemented.
- Public APIs are exported through `__init__.py` intentionally.
- Module names describe capabilities, not implementation generations.
- No files named `new`, `old`, `mvp`, `v2`, `final`, or `production` in product code.
- Generated files never live beside source files.
- Architectural decisions live in `docs/architecture/adr`.

## Testing Architecture

### Unit Tests

Target:

- Domain models and policies.
- Application services with fake ports.
- No network, filesystem, Qdrant, Redis, Ollama, or subprocess.

### Contract Tests

Target:

- Every infrastructure adapter must satisfy its port contract.
- OpenAI-compatible route behavior.
- Tool permission and sandbox contracts.
- Model router fallback contracts.

### Integration Tests

Target:

- FastAPI app with test container.
- Qdrant adapter against containerized Qdrant or in-memory fake.
- Redis cache adapter if enabled.
- Filesystem/vault adapter with temporary directories.
- Git adapter with temporary repos.

### E2E Tests

Target:

- CLI task run.
- API agent run and stream.
- Desktop smoke flow.
- Tool execution audit trail.
- Memory ingestion and retrieval.

## Deployment Architecture

### Processes

- `anubis-api`: FastAPI HTTP server.
- `anubis-worker`: background ingestion/maintenance worker.
- `anubis-cli`: terminal client/runner.
- `anubis-desktop`: Tauri desktop shell.

All processes use the same `bootstrap/container.py` and `bootstrap/settings.py`.

### External Dependencies

- Qdrant: vector store.
- Redis: optional cache and queue support.
- Ollama: optional local model provider.
- Remote model APIs: optional providers via secrets.
- Filesystem vault: source of truth for notes/skills if enabled.

### Configuration

- `.env.example` documents all settings.
- Environment-specific config is injected through env vars.
- No code reads env vars outside `bootstrap/settings.py` or secret infrastructure.

### Observability

- Structured logs.
- Tool audit JSONL or pluggable audit sink.
- Health/readiness endpoints.
- Model/provider health.
- Vector store and cache health.
- Agent run events and trace IDs.

## Migration Destination Mapping

Current duplicate sources should migrate as follows:

```text
backend/agent/core_loop.py          -> anubis/application/agents/*
backend/agent/multi_agent.py        -> anubis/application/agents/*
backend/agent/verifier.py           -> anubis/application/agents/verifier.py
backend/tools/sandbox.py            -> anubis/infrastructure/process/sandbox.py
anubis/tools/base.py                -> anubis/domain/tools/models.py + application/tools
backend/rag/qdrant_store.py         -> anubis/infrastructure/vector_store/qdrant.py
retrieval/*                         -> anubis/application/memory/*
backend/context/*                   -> anubis/application/memory/*
backend/api/routes/*                -> anubis/interfaces/api/routes/*
app/main.py OpenAI compatibility    -> anubis/interfaces/api/routes/openai_compat.py
backend/core/config.py + config.py  -> anubis/bootstrap/settings.py
anubis/cli/*                        -> anubis/interfaces/cli/*
src/ + src-tauri/                   -> apps/desktop/
desktop-ui/                         -> migrate useful UI patterns or archive
cli_mvp/ and root cli/              -> delete after command parity
```

## Acceptance Criteria For Target State

The architecture is complete when:

- `pyproject.toml` packages only `anubis`.
- There is one API app factory.
- There is one CLI entrypoint.
- There is one desktop app.
- There is one agent loop.
- There is one tool execution pipeline.
- There is one memory/RAG pipeline.
- There is one typed settings system.
- No production code imports root legacy packages.
- No production code imports `backend`.
- Unit tests can run without external services.
- Integration tests identify every external dependency explicitly.
- Dependency rules are enforced in CI.

## Non-Goals

- Keep every historical implementation.
- Preserve duplicate API paths forever.
- Support three frontend runtimes.
- Let plugins bypass tool policy.
- Let route handlers own business logic.
- Let model-provider details leak into agent planning/execution.

## Final Shape

Anubis should become a single product with multiple adapters, not multiple products in one repo. The target architecture is:

```text
Desktop / CLI / API / Worker
          |
      Bootstrap
          |
   Application Services
          |
   Domain + Ports
          |
 Infrastructure Adapters
```

That shape gives the project a stable core, replaceable integrations, multi-model support, safer tool execution, easier onboarding, and a codebase that multiple developers and AI agents can navigate without guessing which generation of the system is real.
