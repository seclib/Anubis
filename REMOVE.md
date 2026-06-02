# REMOVE

Strategic rule: remove anything that only supports Desktop, Tauri, React, Vite, frontend dashboards, abandoned UI experiments, or duplicate service architectures that do not strengthen the terminal agent.

Nothing should be deleted until the migration plan has tests and replacement paths.

## Remove: Desktop, Tauri, React, Vite

High-confidence removal candidates:

- `desktop/`
  - Reason: full Tauri/React desktop product is no longer strategic.
  - Includes:
    - `desktop/src/`
    - `desktop/src-tauri/`
    - `desktop/package.json`
    - `desktop/package-lock.json`
    - `desktop/vite.config.ts`
    - `desktop/tailwind.config.js`
    - `desktop/tsconfig.json`
    - `desktop/dist/`
    - `desktop/node_modules/`

- `anubis/apps/desktop/`
  - Reason: duplicate desktop experiment.
  - Includes React/Vite/Tauri duplicate app.

- `Anubis.desktop`
  - Reason: Linux desktop launcher for obsolete product surface.

- `launcher/`
  - Reason: desktop launcher/service-manager documentation and manifest.

- `scripts/install_desktop_entry.sh`
  - Reason: installs obsolete desktop launcher.

- `scripts/launch_anubis_desktop.sh`
  - Reason: launches obsolete desktop product.

- `frontend/`
  - Reason: frontend-only placeholder, no role in terminal-first architecture.

## Remove: Desktop-Specific API Surfaces

Remove or heavily rewrite:

- `backend/api/routes/desktop.py`
  - Reason: desktop/library/assistant convenience API. Terminal and Obsidian workflows should own this.

- `backend/api/routes/brain.py`
  - Reason: React dashboard snapshot/log surface with desktop assumptions.
  - Replacement: terminal status panel and simple health/status command.

- Desktop expectations in:
  - `backend/main.py`
  - `tests/test_backend_desktop_api.py`
  - `Makefile`
  - `start.sh`
  - `scripts/check.sh`
  - `scripts/setup.sh`

## Remove: Duplicate GUI Dependencies

Remove from package manifests once desktop folders are removed:

- `@tauri-apps/api`
- `@tauri-apps/cli`
- `@vitejs/plugin-react`
- `vite`
- `typescript` if only used by deleted desktop/plugin code
- `react`
- `react-dom`
- `tailwindcss`
- `postcss`
- `autoprefixer`
- `d3`
- `cytoscape`
- `lucide-react`
- Rust/Tauri build dependencies under `desktop/src-tauri`

Keep TypeScript only for the Obsidian plugin if that plugin survives.

## Remove: Node RAG Service

Candidate:

- `rag-system/src/`
- `rag-system/package.json`
- `rag-system/package-lock.json`

Reason:

- Duplicates Python RAG, Qdrant, ingestion, and `/ask` logic.
- Current plugin points to `http://127.0.0.1:8787/sync`; this should be redirected to the terminal/FastAPI backend or replaced by filesystem watcher sync.

Keep only:

- `rag-system/obsidian-plugin/` temporarily, then move to `obsidian-plugin/`.

## Remove Or Archive: Service-Oriented Monorepo Experiment

Candidate:

- `anubis/services/ai-core/`
- `anubis/services/rag/`
- `anubis/services/tools/`
- `anubis/packages/`
- `anubis/kernel/`
- `anubis/apps/desktop/`

Reason:

- This is a parallel architecture with many packages and services.
- It conflicts with Karpathy-style minimalism.
- It is not the currently functional terminal-first product.

Before removal, salvage:

- RAG security filters from `anubis/services/rag/security/`.
- Tool sandbox schemas/permissions from `anubis/services/tools/`.
- Agent trace examples/docs from `anubis/docs/`.
- Minimal kernel ideas if they simplify the canonical agent.

## Remove Or Merge: Legacy Root API Stack

Candidate after terminal/backend consolidation:

- `app/`
- `api/`
- `services/`
- `workers/`
- `monitoring/`
- `intelligence/`

Reason:

- Duplicates the current `backend/` FastAPI API.
- Pulls in crawler/cache/background systems not central to terminal-first agent.
- Makes operational path ambiguous: Dockerfile uses `app.main`, Makefile uses `backend.main`.

Replacement:

- One optional FastAPI app under `anubis/api/` or canonical `backend/main.py`.

## Remove Or Merge: Duplicate Memory/RAG Systems

Remove after useful code is merged:

- `rag/`
- `retrieval/`
- `knowledge/`
- `storage/`
- parts of `memory/`

Reason:

- There are too many parallel RAG/memory systems.
- Target memory is simple:
  - Obsidian files are truth.
  - Qdrant stores embeddings.
  - terminal agent retrieves before reasoning.

Salvage before removal:

- `retrieval/confidence.py`
- `retrieval/context_builder.py`
- `retrieval/query_planner.py`
- `retrieval/fusion.py`
- `retrieval/hybrid.py`
- `storage/keyword_index.py`
- any robust Qdrant retry/error handling from `storage/qdrant.py`

## Remove Or Merge: Duplicate Agent Systems

The repo currently has several:

- root `agent/`
- `backend/agent/`
- `anubis/kernel/src/anubis_kernel/agent/`
- `anubis/services/ai-core/src/anubis_ai_core/agent/`
- `anubis/services/ai-core/src/anubis_ai_core/orchestrator/`

Removal strategy:

- Keep root `agent/` temporarily because terminal autonomy tests depend on it.
- Keep `backend/agent/` temporarily because it integrates with current RAG/API.
- Merge the best pieces into one `anubis/agent/`.
- Remove the rest.

## Remove Generated And Runtime Artifacts

Should not be source-controlled:

- `.venv/`
- `__pycache__/`
- `*.pyc`
- `desktop/node_modules/`
- `desktop/dist/`
- `desktop/src-tauri/target/`
- `state/*.log`
- `state/dev_servers/`
- temporary setup/dev output

Review before deleting:

- `state/obsidian_vault/`
- `state/hermes_memory.json`
- `state/query_cache.json`
- `state/cli_session.jsonl`

Some contain useful historical memory; migrate durable knowledge into `vault/`.

## Remove Roadmap Items

Do not add new work for:

- Desktop dashboards.
- Tauri service management.
- React skill graph UI.
- Vite frontend refactors.
- Electron-like shells.
- GUI-first onboarding.
- Desktop packaging.
- Desktop tray/menu systems.

Terminal and Obsidian are the interfaces.

