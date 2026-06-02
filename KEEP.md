# KEEP

Strategic direction: Anubis is now terminal-first. Keep code that directly supports the terminal agent, Obsidian knowledge, Qdrant memory, autonomous reasoning, skill learning, and controlled tool execution.

## Canonical Product Surface

Keep and consolidate around these components:

- `cli/`
  - Purpose: terminal interface, command handling, session rendering, user input, terminal theme.
  - Why keep: terminal is now the primary product surface.
  - Refactor target: modernize into the main Anubis TUI/CLI experience.

- `anubis_cli.py`
  - Purpose: CLI entrypoint.
  - Why keep: simple terminal launch path.
  - Refactor target: rename or wrap as `anubis` console script.

- `runtime/`
  - Purpose: connects agent loop, LLM caller, tools, memory dependencies, streaming events.
  - Why keep: currently powers the terminal agent stack.
  - Refactor target: merge into `anubis/agent/` and `anubis/sandbox/` once the new structure exists.

- `agent/`
  - Purpose: autonomous terminal agent system: planner, orchestrator, coder, reviewer, tester, debugger, memory agent, self-improvement, streaming.
  - Why keep: this is the functional agent core with the most current value.
  - Refactor target: simplify into planner/executor/critic plus optional specialist roles.

- `tools/`
  - Purpose: terminal, repo, filesystem, git, sandbox, memory, dynamic tools.
  - Why keep: controlled tool execution is central to autonomous terminal work.
  - Refactor target: harden permissions and merge with `backend/tools/sandbox.py`.

- `executor/`
  - Purpose: lower-level tool execution abstraction.
  - Why keep: used by `runtime/plugins.py` and `runtime/tool_registry.py`.
  - Refactor target: merge into one sandbox/tool execution layer.

## RAG, Memory, Qdrant, Obsidian

- `backend/rag/`
  - Purpose: current compact chunk/embed/index/search layer over Qdrant.
  - Why keep: simplest aligned Qdrant implementation.
  - Refactor target: become `anubis/rag/`.

- `backend/vault/`
  - Purpose: Markdown vault file service and parser.
  - Why keep: Obsidian is the source of truth.
  - Refactor target: become `anubis/obsidian/`.

- `backend/watcher/`
  - Purpose: watchdog-based real-time Markdown ingestion.
  - Why keep: live Obsidian sync is core architecture.
  - Refactor target: become `anubis/obsidian/watcher.py`.

- `backend/skills/`
  - Purpose: Markdown skill repository and skill generation.
  - Why keep: skill learning is a core product direction.
  - Refactor target: remove legacy dependencies and make skills first-class Obsidian files.

- `backend/agent/`
  - Purpose: newer API-oriented agent loop, async planner/executor/critic, LLM adapter, meta-agent.
  - Why keep: useful simpler implementation for production API and RAG-grounded loops.
  - Refactor target: merge with root `agent/` rather than keeping two agent systems.

- `backend/tools/`
  - Purpose: minimal sandbox executor.
  - Why keep: good production-oriented sandbox base.
  - Refactor target: merge with root `tools/sandbox.py`.

- `backend/core/`
  - Purpose: config, logging, path safety.
  - Why keep: clean reusable backend primitives.
  - Refactor target: become `anubis/config/` and shared path helpers.

- `memory/`
  - Purpose: legacy runtime state, vector fallback, Hermes memory, query cache.
  - Why keep short-term: terminal stack still depends on it.
  - Refactor target: migrate durable memory to Obsidian + Qdrant, keep only ephemeral session state.

- `retrieval/`
  - Purpose: richer retrieval pipeline: query planning, confidence, hybrid search, context building.
  - Why keep selectively: contains quality improvements not present in `backend/rag`.
  - Refactor target: merge useful pieces into `anubis/rag/`; do not preserve as a parallel subsystem.

- `storage/qdrant.py`
  - Purpose: older Qdrant adapter.
  - Why keep selectively: may contain operational details missing from `backend/rag/qdrant_store.py`.
  - Refactor target: merge useful pieces, then remove old storage layer.

- `storage/keyword_index.py`
  - Purpose: keyword fallback search.
  - Why keep selectively: hybrid search can improve RAG quality.
  - Refactor target: merge into `anubis/rag/hybrid.py`.

- `vault/`
  - Purpose: local development Obsidian-style vault with notes and skills.
  - Why keep: file-based truth and local defaults.

- `state/obsidian_vault/`
  - Purpose: existing memory notes and historical knowledge.
  - Why keep as data if valuable.
  - Refactor target: migrate useful notes into canonical `vault/`, archive the rest.

## API And Service Layer

- `backend/main.py`
  - Purpose: FastAPI app with production routes and watcher lifecycle.
  - Why keep: useful API for terminal automation, local integrations, Obsidian plugin, and future headless use.
  - Refactor target: API is secondary to terminal, but still valuable.

- `backend/api/routes/production.py`
  - Purpose: `/ask`, `/sync`, `/memory`.
  - Why keep: maps exactly to terminal/agent/RAG operations.

- `backend/api/routes/health.py`
  - Purpose: health/ready checks.
  - Why keep: production operations.

- `api/openai_server.py`
  - Purpose: legacy OpenAI-compatible server.
  - Why keep only if compatibility is required.
  - Refactor target: optional adapter, not core architecture.

## Infrastructure

- `Makefile`
  - Keep but rewrite around terminal-first commands:
    - `make anubis`
    - `make test`
    - `make qdrant`
    - `make sync`
    - remove `make desktop`.

- `docker-compose.yml`
  - Keep Qdrant service.
  - Remove desktop assumptions.
  - Update backend container to canonical terminal/API runtime if containerized use matters.

- `infra/qdrant/`
  - Keep Qdrant production config.

- `scripts/`
  - Keep:
    - `scripts/check.sh`
    - `scripts/dev_backend.sh`
    - `scripts/ingest_obsidian.py`
    - `scripts/run_agent.py`
    - `scripts/run_multi_agent.py`
    - `scripts/run_skill_engine.py`
    - `scripts/run_meta_agent.py`
    - `scripts/watch_obsidian.py`
    - git identity/audit helpers if still used.
  - Refactor setup scripts around terminal + Qdrant only.

## Tests

- `tests/test_loop_autonomy.py`
  - Keep short-term because it validates the functional terminal/autonomy stack.
  - Refactor to the new canonical `anubis/agent` package.

- `tests/test_backend_desktop_api.py`
  - Keep only the non-desktop assertions.
  - Rename and split into:
    - `test_api.py`
    - `test_obsidian.py`
    - `test_rag.py`
    - `test_agent_loop.py`

## Documentation

Keep and rewrite around terminal-first architecture:

- `README.md`
- `AUDIT_REPORT.md`
- `docs/ANUBIS_MINIMAL_AGENT.md`
- `docs/ARCHITECTURE.md`
- `docs/GIT_WORKFLOW.md`
- `docs/LOCAL_API.md`
- `docs/PRODUCTION_KNOWLEDGE_ASSISTANT.md`
- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/USER_GUIDE.md`
- `anubis/docs/AGENT_SYSTEM.md`
- `anubis/docs/MULTI_AGENT_ORCHESTRATION.md`
- `anubis/docs/SECURE_RAG_PIPELINE.md`
- `anubis/docs/SECURE_TOOL_SANDBOX.md`

## Optional Keep, Only If Reframed

- `rag-system/obsidian-plugin/`
  - Keep only if Obsidian plugin remains a secondary interaction layer.
  - Retarget to terminal/FastAPI/Qdrant backend.
  - Do not use it to resurrect a GUI-first product.

- `crawler/`
  - Keep only as an explicit terminal tool or skill for web ingestion.
  - Otherwise remove.

- `monitoring/`
  - Keep only if exposed as terminal status panels or simple `/health` metrics.
  - Otherwise merge into simpler logging/status.

- `anubis/services/rag/security/`
  - Keep the ideas: memory guard, sanitizer, injection filters.
  - Merge into canonical RAG ingestion.

