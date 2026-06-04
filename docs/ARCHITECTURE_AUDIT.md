# Architecture Audit

Date: 2026-06-04

Scope: full repository audit of the current on-disk state, excluding dependency/build/runtime artifacts such as `.git`, `.venv`, `node_modules`, `dist`, `.next`, `src-tauri/target`, and `state` where practical. The workspace already contains uncommitted changes; this audit treats them as current source state and does not attempt to revert or normalize them.

## 1. Current Architecture Overview

Anubis currently contains multiple overlapping products and architectural generations in one repository:

- Root Python runtime: `main.py`, `app/`, `api/`, `runtime/`, `agent/`, `memory/`, `retrieval/`, `storage/`, `knowledge/`, `crawler/`, `services/`, `workers/`, `tools/`.
- Newer packaged Python runtime: `anubis/`, including `anubis/cli`, `anubis/core`, `anubis/agents`, `anubis/context`, `anubis/memory`, `anubis/tools`, `anubis/orchestration`, `anubis/distributed`, `anubis/dsl`, `anubis/ui`, and `anubis/workspace`.
- Backend-specific Python runtime: `backend/`, including FastAPI routes, agent loops, RAG, vault, watcher, tools, skills, security, and context.
- Frontend runtimes:
  - Root Vite/Tauri app in `src/` + `src-tauri/`.
  - Nested scaffold Vite/Tauri app in `anubis/src/` + `anubis/src-tauri/`.
  - Separate Next app in `desktop-ui/`.
  - Separate JavaScript RAG/Obsidian plugin system in `rag-system/`.
- Infrastructure and deployment spread across root Docker files, `docker/`, `infra/`, `scripts/`, `.github/workflows/`, and package scripts.
- Persistent/application data and generated artifacts are present in the repository tree: `.venv`, `node_modules`, Tauri targets, `__pycache__`, logs, `state`, and generated schemas. Some are ignored by `.gitignore`; some are still present on disk and contaminate discovery.

Measured source size after excluding obvious generated/dependency folders:

- 524 Python files.
- About 71,703 lines across Python/TypeScript/JavaScript/Rust source-like files.
- Python line distribution is heavily fragmented: `anubis/` has ~22.4k LOC, `backend/` ~11.9k LOC, root `agent/` ~6.2k LOC, `tests/` ~9.6k LOC, plus many smaller root packages.

The nominal package definition in `pyproject.toml` declares `anubis-cli` and exposes `anubis = "anubis.cli.main:main"`, but setuptools only includes `anubis*`, `cli*`, `backend*`, and `cli_mvp*`. Many root packages that active files import (`runtime`, `memory`, `retrieval`, `storage`, `services`, `knowledge`, `crawler`, `tools`, `app`, `config`) are not included in that packaging rule.

## 2. Major Problems

### There Is No Single Architecture

The repository does not have one architecture with messy areas. It has several partially overlapping architectures:

- `app/main.py` is a large OpenAI-compatible API server wired to root packages.
- `backend/main.py` is a separate FastAPI server wired to `backend/api/routes/*`.
- `api/openai_server.py` appears to be another API entry layer.
- `anubis/` is described as an architecture scaffold in `anubis/README.md`, but it already contains large implemented subsystems, including `anubis/distributed`.
- `main.py` presents "Anubis Agent V4" and imports root runtime packages directly.

This makes ownership ambiguous. It is not clear whether `backend/`, root packages, or `anubis/` is canonical.

### Module Boundaries Are Repeated Instead Of Layered

Nearly every core concept exists in multiple places:

- Agent loop: `agent/loop.py`, `backend/agent/loop.py`, `backend/agent/core_loop.py`, `backend/agent/agent_loop.py`, `anubis/core/agent_loop/loop.py`, `anubis/agents/loop.py`.
- Planner/executor/verifier: root `agent/`, `backend/agent/`, `anubis/agents/`, and `anubis/core/*`.
- Tools: `tools/`, `backend/tools/`, `anubis/tools/`.
- RAG/context/retrieval: `rag/`, `retrieval/`, `backend/rag/`, `backend/context/`, `anubis/context/`, `anubis/memory/`.
- Configuration: `config.py`, `backend/core/config.py`, `anubis/core/config.py`.
- Logging/path utilities: root `core/`, `backend/core/`, `anubis/core/`, `anubis/utils/`.
- UI API surfaces: root `src/app/core/api.ts`, backend routes, Tauri commands, `desktop-ui`.

These are not clean ports/adapters. They are competing implementations.

### Circular Dependencies Exist At Package Level

Static import analysis found strongly connected top-level components:

- `anubis` <-> `backend`
- `crawler`, `knowledge`, `rag`, `retrieval`, `services`, `storage`, `workers`

Direct two-way package edges include:

- `anubis` <-> `backend`
- `knowledge` <-> `storage`

There is also a direct module-level cycle:

- `backend.agent.executor` <-> `backend.agent.verifier`

These cycles violate clean architecture dependency direction. Domain/application code depends on infrastructure, API code reaches into services directly, and storage/retrieval/knowledge depend back on each other.

### Packaging Is Broken Or Misleading

`pyproject.toml` only packages `anubis*`, `cli*`, `backend*`, and `cli_mvp*`, while major runnable paths import non-packaged root modules:

- `main.py` imports `app.main`, `runtime.agent_runner`, `memory.state`, and `config`.
- `app/main.py` imports `runtime`, `crawler`, `intelligence`, `knowledge`, `retrieval`, `services`, `rag`, `storage`, `workers`, `monitoring`, and `config`.
- root `cli/` imports `runtime`, `backend`, `memory`, `retrieval`, `llm`, and `config`.

An installed package can easily diverge from the development checkout.

### API Layers Are Duplicated And Inconsistent

The repo contains at least three API styles:

- Root OpenAI-style server in `app/main.py`.
- Legacy/root API modules in `api/routes/*` and `api/openai_server.py`.
- Backend/Desktop API in `backend/main.py` with `backend/api/routes/*`.

The frontend calls `/ask` and `/health/live` in `src/app/core/api.ts`, while `backend/main.py` mounts production routes and many `/api/*` routes. The existence of `backend/api/routes/desktop.py`, `local.py`, `production.py`, `rag.py`, and root `api/routes/rag.py` indicates route responsibilities have grown by copy/addition rather than by a single contract.

### Frontend Architecture Is Split

There are three frontend surfaces:

- Root Tauri/Vite app: `src/` and `src-tauri/`.
- Nested Tauri/Vite scaffold: `anubis/src/` and `anubis/src-tauri/`.
- Next desktop UI: `desktop-ui/`.

Duplicate UI files include:

- `src/app/ui/InputBar.tsx` and `desktop-ui/components/InputBar.tsx`.
- `src/app/ui/CommandPalette.tsx` and `desktop-ui/components/CommandPalette.tsx`.
- `src/app/App.tsx` and `anubis/src/App.tsx`.
- root `vite.config.ts` and `anubis/vite.config.ts`.
- root `src-tauri/tauri.conf.json` and `anubis/src-tauri/tauri.conf.json`.

No clear decision is encoded about which UI is production.

### Tests Reinforce The Split Instead Of Constraining It

Tests import across `anubis`, `backend`, root `agent`, root `cli`, `runtime`, `retrieval`, `memory`, and `tools`. That means the tests currently validate multiple architectures instead of enforcing a single intended one.

Examples from import analysis:

- `tests -> anubis`: 49 import edges.
- `tests -> backend`: 21 import edges.
- `tests -> agent`: 13 import edges.
- `tests -> cli`: 6 import edges.

This makes refactoring hazardous because tests are likely coupled to transitional and duplicate implementations.

## 3. Critical Risks

### High Risk: Undefined Runtime Canonicality

There is no authoritative runtime. A developer can reasonably start `main.py`, `backend.main:app`, `app.main:app`, Tauri root, nested Tauri, or Next. Each path reaches different services and configuration.

Impact: bug fixes land in the wrong layer, features work in one runtime and fail in another, and production packaging becomes unpredictable.

### High Risk: Architectural Drift Will Accelerate

New functionality has too many possible homes. A new memory feature could go into `memory/`, `anubis/memory/`, `backend/rag/`, `backend/context/`, `retrieval/`, or `storage/`. A new tool could go into `tools/`, `backend/tools/`, or `anubis/tools/`.

Impact: every feature increases duplication and makes later consolidation more expensive.

### High Risk: Clean Architecture Is Inverted

Application/domain concepts directly import infrastructure and concrete framework modules. API routes construct or retrieve concrete services. Storage, retrieval, workers, and knowledge form a cycle.

Impact: hard-to-test business logic, hidden side effects, and no stable domain core.

### High Risk: Security Boundaries Are Not Centralized

Sandbox/tool/security concepts exist in several places:

- `backend/tools/sandbox.py`
- `tools/sandbox.py`
- `anubis/tools/sandbox.py`
- `backend/security/*`
- `anubis/distributed/filesystem_jail.py`
- `anubis/distributed/network_isolation.py`
- `anubis/distributed/permission_manager.py`

Impact: one route or agent may use a hardened path while another uses a permissive or stale path.

### Medium Risk: Configuration Sprawl

`config.py` is a large environment-variable module. `backend/core/config.py` is a separate Pydantic settings object with different defaults. `anubis/core/config.py` exists but is empty. Frontend config is split between root Vite, nested Vite, Next, Tauri, Docker Compose, and scripts.

Impact: local/dev/prod behavior will differ silently.

### Medium Risk: Generated And Runtime Artifacts Distort The Repo

`.venv`, `node_modules`, Tauri targets, `__pycache__`, and state/log files are present in the working tree. Even if ignored, their presence makes tooling, search, and audits noisy.

Impact: slower tooling, accidental commits, and false-positive architecture discovery.

## 4. Redundant Components

Likely redundant or overlapping components:

- `agent/` vs `backend/agent/` vs `anubis/agents/` vs `anubis/core/agent_loop/`.
- `cli/` vs `cli_mvp/` vs `anubis/cli/` vs `anubis_cli.py` vs `anubis_cli_mvp/`.
- `tools/` vs `backend/tools/` vs `anubis/tools/`.
- `memory/` vs `anubis/memory/` vs `retrieval/` vs `rag/` vs `backend/rag/` vs `backend/context/` vs `anubis/context/`.
- `api/` vs `app/` vs `backend/api/`.
- `src/` vs `desktop-ui/` vs `anubis/src/`.
- `src-tauri/` vs `anubis/src-tauri/`.
- `llm/ollama.py` vs `anubis/llm/ollama.py` vs `backend/agent/llm.py`.
- `core/`, `backend/core/`, `anubis/core/`, and `anubis/utils/`.
- `infra/docker/*`, root `Dockerfile`, `docker/entrypoint.sh`, root `docker-compose.yml`, and multiple compose files under `infra/docker/`.

Files/folders that should probably be removed after migration, not immediately:

- `cli_mvp/` and `anubis_cli_mvp/` if `anubis/cli` is canonical.
- Nested `anubis/src/` and `anubis/src-tauri/` if root `src/` + `src-tauri/` is canonical.
- Root `agent/` after any still-used logic is migrated into one application layer.
- Root `api/` after routes are consolidated under one FastAPI app.
- Root `rag/` after retrieval/RAG is unified.
- One of `desktop-ui/` or root Tauri UI, unless there is a documented product reason to keep both.

## 5. Duplicate Logic

Duplicate basenames and classes indicate real architectural duplication, not harmless naming:

- `service.py`: 8 files.
- `interfaces.py`: 8 files.
- `logging.py`: 5 files.
- `loop.py`: 5 files.
- `main.py`: 5 files.
- `parser.py`: 5 files.
- `registry.py`: 5 files.
- `router.py`: 5 files.
- `planner.py`: 4 files.
- `prompts.py`: 4 files.
- `retriever.py`: 4 files.
- `session.py`: 4 files.
- `state.py`: 4 files.
- `terminal.py`: 4 files.

Duplicate or overlapping classes include:

- `AgentLoop`: 4 definitions.
- `Planner`: 4 definitions.
- `Executor`: 4 definitions.
- `Plan`: 4 definitions.
- `PlanStep`: 4 definitions.
- `StepResult`: 4 definitions.
- `ContextCompressor`: 3 definitions.
- `SearchRequest`: 3 definitions.
- `SkillCritic`: 3 definitions.
- `ToolResult`: multiple definitions across `anubis/types.py`, `backend/tools/*`, and tool layers.

Potentially unreferenced modules from static import analysis include many files under `anubis/agents`, `anubis/orchestration`, `anubis/memory`, `anubis/ui`, `api/routes`, and `backend/api/routes`. This is not proof of dead code because some may be entrypoints or dynamically imported, but it is strong evidence that the repo has accumulated inactive or aspirational modules.

## 6. Recommended New Architecture

Pick one canonical product architecture and make every folder prove its role. Recommended target:

```text
anubis/
  domain/
    agents/
    memory/
    tools/
    tasks/
    workspace/
    security/
  application/
    agent_loop/
    orchestration/
    retrieval/
    skill_runtime/
    sessions/
  ports/
    llm.py
    vector_store.py
    file_system.py
    shell.py
    git.py
    event_bus.py
  infrastructure/
    ollama/
    qdrant/
    obsidian/
    local_shell/
    git_cli/
    persistence/
  interfaces/
    cli/
    api/
    desktop/
  shared/
    config.py
    logging.py
    paths.py
```

Rules:

- Domain has no FastAPI, Tauri, Qdrant, Ollama, subprocess, HTTP, or filesystem side effects.
- Application services depend on domain and ports only.
- Infrastructure implements ports.
- API/CLI/Desktop are adapters that call application services.
- Tests should target domain/application first, then adapter contracts.
- `backend/`, root service packages, and legacy folders should become migration sources, not permanent peers.

Canonical runtime recommendation:

- Python package: `anubis`.
- API adapter: `anubis/interfaces/api`.
- CLI adapter: `anubis/interfaces/cli` or keep `anubis/cli` but make it an adapter only.
- Desktop frontend: root `src/` + `src-tauri/`, unless the team explicitly chooses Next. Do not keep root Vite, nested Vite, and Next all as first-class production UIs.
- RAG/memory: one application service with ports for vector store, keyword index, vault, and embedding provider.
- Tools/security: one tool execution pipeline with a single policy engine and audit logger.

## 7. Refactoring Roadmap

### Phase 0: Freeze And Decide

- Declare the canonical runtime in `docs/` and `README.md`.
- Mark non-canonical folders as legacy/migration-only.
- Decide whether production UI is root Tauri/Vite, nested `anubis` Tauri/Vite, or `desktop-ui` Next.
- Decide whether production API is `backend/main.py` or `app/main.py`.
- Add an architecture rule: no new features in legacy duplicate folders.

### Phase 1: Repository Hygiene

- Remove generated/runtime artifacts from the working tree where tracked or accidentally present.
- Expand `.gitignore` for `.venv/`, nested generated files, all `__pycache__/`, generated Tauri schemas, local logs, and runtime state.
- Add a source-only file listing command/script for audits.
- Make package discovery match runtime imports.

### Phase 2: Establish A Single Composition Root

- Create one application container/composition root.
- Move configuration to one typed settings module.
- Make API, CLI, workers, and desktop commands receive dependencies from that composition root.
- Remove direct construction of concrete services from route handlers.

### Phase 3: Collapse Duplicate Agent Loops

- Choose one planner/executor/verifier/critic model.
- Merge useful logic from `agent/`, `backend/agent/`, `anubis/agents/`, and `anubis/core/*`.
- Keep interfaces in ports/application; keep concrete LLM/tool implementations in infrastructure.
- Delete superseded agent modules after tests are migrated.

### Phase 4: Collapse Memory/RAG/Context

- Define one retrieval use case: ingest, index, retrieve, query, summarize.
- Merge `memory/`, `retrieval/`, `rag/`, `backend/rag/`, `backend/context/`, `anubis/context/`, and `anubis/memory/`.
- Make Qdrant, Redis, local JSON, Obsidian, and embeddings infrastructure adapters.
- Remove circular dependencies among knowledge, storage, retrieval, workers, and services.

### Phase 5: Collapse Tool And Security Layers

- Define one `ToolRequest -> Policy -> Executor -> AuditLog -> ToolResult` pipeline.
- Merge or delete duplicate sandbox/filesystem/shell/git implementations.
- Route every agent, API, CLI, and desktop tool call through that pipeline.
- Add contract tests for dangerous commands, path traversal, network access, and audit logging.

### Phase 6: Consolidate API And UI

- Replace `api/`, `app/`, and `backend/api/` with one API adapter.
- Generate or centralize frontend API clients from that adapter's contract.
- Delete duplicate frontend implementations after the chosen UI can perform the supported workflows.
- Keep Tauri commands thin and route them to the same API/application layer.

### Phase 7: Delete Legacy Code

- Remove folders only after call sites and tests are migrated.
- Start with `cli_mvp/`, `anubis_cli_mvp/`, nested scaffold UI, root `rag/`, and root `api/` if they are confirmed non-canonical.
- Then remove root `agent/`, root `tools/`, and root `memory/` once functionality exists under the canonical package.

## 8. Estimated Complexity

Overall complexity: Very High.

This is not a small cleanup. It is a staged consolidation of several partially implemented systems.

Estimated effort:

- Architecture decision record and freeze: 1-2 days.
- Repository hygiene and packaging repair: 1-3 days.
- Single composition root/config: 3-5 days.
- Agent loop consolidation: 1-2 weeks.
- Memory/RAG/context consolidation: 1-3 weeks.
- Tool/security consolidation: 1-2 weeks.
- API/UI consolidation: 1-3 weeks depending on chosen UI.
- Legacy deletion and test migration: 1-2 weeks.

Likely total: 5-10 engineering weeks for one senior engineer, less with disciplined parallel ownership, more if feature work continues during the refactor.

Refactoring risk level:

- High for API and agent loop behavior.
- High for memory/RAG correctness.
- High for tool security.
- Medium for frontend consolidation.
- Medium for packaging and config once the canonical runtime is chosen.

The most important recommendation is to stop treating all existing folders as equally valid. This repository needs architectural deletion as much as architectural design.
