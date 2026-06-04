# CTO_REVIEW.md

## Executive Position

This repository was drifting toward architecture theater: several folders existed to describe an ideal architecture, but the running product still lived in `backend`, `anubis.cli`, and `anubis.distributed`. That made the codebase harder to reason about without improving correctness, scalability, or developer experience.

The CTO decision is simple: keep the code that owns behavior, remove pass-through layers, and consolidate around fewer production entrypoints.

## What Was Removed

### Removed Clean-Architecture Wrapper Layer

Deleted the generated wrapper packages:

- `anubis/application`
- `anubis/bootstrap`
- `anubis/domain`
- `anubis/infrastructure`
- `anubis/interfaces`
- `anubis/ports`
- `anubis/shared`

Reason:

These directories contained mostly thin adapters, dataclasses, protocol definitions, and facades that delegated back to `backend` or `anubis.distributed`. They did not own production behavior, enforce meaningful boundaries, or reduce risk. They added import depth and onboarding cost.

### Removed Nested Frontend Scaffold

Deleted the duplicate Vite/Tauri scaffold inside the Python package:

- `anubis/package.json`
- `anubis/package-lock.json`
- `anubis/vite.config.ts`
- `anubis/tsconfig.json`
- `anubis/tsconfig.node.json`
- `anubis/src`
- `anubis/src-tauri`
- `anubis/node_modules`

Reason:

The root frontend is the active application. The nested frontend had a different dependency set and React version, creating split-brain UI ownership and dependency confusion.

### Removed Generated Build/Caches

Deleted tracked and untracked generated artifacts:

- Python `__pycache__` directories
- `*.pyc` files
- `src-tauri/target`

Reason:

Generated outputs do not belong in source control. They make diffs noisy, increase repository size, and confuse maintainers.

## What Was Merged

### CLI Entry Point

Changed `pyproject.toml`:

- Before: `anubis = "anubis.interfaces.cli.main:main"`
- After: `anubis = "anubis.cli.main:main"`

Reason:

`anubis.interfaces.cli.main` was a pass-through wrapper. The actual CLI already exists in `anubis.cli.main`; production should point directly at the implementation.

### API Ownership

Kept `backend.main:app` as the real API entrypoint.

Reason:

`backend.main` owns the actual route registration, startup hooks, watcher integration, and health routes. The deleted `anubis.interfaces.api.app` only returned `backend.main.app`.

## What Was Simplified

### Active Architecture

The practical architecture is now:

- `backend`: FastAPI API, vault, RAG, local tools, production routes.
- `anubis.cli`: terminal-first CLI.
- `anubis.core`: CLI/session runtime.
- `anubis.llm`: local Ollama routing/client.
- `anubis.distributed`: tested autonomous-agent orchestration and sandbox services.
- `src`: active React frontend.
- `src-tauri`: active desktop shell.
- `tests`: regression and integration tests.

This is still imperfect, but it is more honest. The codebase now exposes fewer fake boundaries.

### Terminal Safety

The previous QA fix remains in place:

- `anubis/distributed/sandbox_runtime.py` rejects dangerous executables, absolute host paths, shell control surfaces, and inline interpreter execution.
- `tests/test_terminal_service.py` includes regression coverage.

This is a production-critical simplification: security policy now sits at the execution boundary instead of being implied by role names.

## Remaining Technical Debt

### 1. `backend` and `anubis` Still Overlap

There are still two large Python namespaces:

- `backend` owns the API/RAG/vault/tool runtime.
- `anubis` owns CLI, distributed systems, local model routing, and newer runtime code.

This is the largest remaining cognitive-load issue. The next consolidation should move toward one Python product namespace, not two.

Recommended direction:

- Keep `anubis` as the package name.
- Migrate `backend.api`, `backend.rag`, `backend.vault`, and `backend.tools` into `anubis` in staged, test-backed moves.
- Do not create new abstraction layers during that migration.

### 2. Too Many Agent Systems

The repository still has multiple agent concepts:

- `backend.agent`
- `anubis.agents`
- `anubis.core.session`
- `anubis.distributed`
- legacy/top-level `agent`
- `cli_mvp`

This is not production-grade yet. It makes it unclear which agent loop is canonical.

Recommended direction:

- Declare one canonical interactive agent runtime.
- Declare one canonical distributed/autonomous runtime.
- Delete or archive the rest after mapping tests and callers.

### 3. Duplicate Frontend Surfaces Remain

The root Vite app is active, but the repo also contains `desktop-ui` and other UI-adjacent directories.

Recommended direction:

- Pick one frontend product path.
- Keep Next only if it is serving a real deployed product.
- Keep Tauri only if desktop packaging is part of the roadmap.
- Otherwise remove extra UI experiments.

### 4. API Route Duplication

Routes still overlap across:

- `backend/api/routes/desktop.py`
- `backend/api/routes/local.py`
- `backend/api/routes/notes.py`
- `backend/api/routes/production.py`
- `backend/api/routes/rag.py`
- `backend/api/routes/vault_workspace.py`

Recommended direction:

- Merge note/vault/filesystem routes behind one workspace API.
- Merge RAG/memory/search routes behind one retrieval API.
- Remove legacy aliases only after frontend and tests use canonical routes.

### 5. FastAPI Lifespan Warnings

Tests still report deprecated `@app.on_event` startup/shutdown handlers in `backend/main.py`.

Recommended direction:

- Replace startup/shutdown event decorators with a FastAPI lifespan context.

### 6. Generated and Runtime State Needs Stronger Ignore Rules

`__pycache__`, `.pyc`, Rust build output, node dependency folders, and runtime state should not reappear in diffs.

Recommended direction:

- Harden `.gitignore`.
- Remove generated artifacts from git history in a dedicated cleanup commit if appropriate.

## Long-Term Roadmap

### Phase 1: Stabilize the Product Surface

- Keep direct entrypoints:
  - API: `backend.main:app`
  - CLI: `anubis.cli.main:main`
  - Frontend: root `src` + root `vite.config.ts`
- Add a short `docs/runtime-map.md` explaining which folders are production-owned.
- Add CI checks for:
  - Python tests
  - frontend build
  - no checked-in `__pycache__`, `node_modules`, or build targets

### Phase 2: Collapse Duplicate Backend APIs

- Define canonical APIs:
  - `/health`
  - `/workspace`
  - `/retrieval`
  - `/agent`
  - `/terminal`
- Move route behavior behind those groups.
- Keep deprecated route aliases temporarily with explicit tests.
- Remove aliases once frontend callers are migrated.

### Phase 3: Choose the Canonical Agent Runtime

- Inventory all agent loops and tests.
- Pick the production runtime.
- Keep `anubis.distributed` only for genuinely distributed/autonomous workflows.
- Delete `agent`, `cli_mvp`, and unused duplicate agent modules once callers are migrated.

### Phase 4: Single Python Namespace

- Migrate `backend` modules into `anubis` in small PRs:
  - `backend.vault` -> `anubis.workspace`
  - `backend.rag` -> `anubis.memory` or `anubis.retrieval`
  - `backend.tools` -> `anubis.tools`
  - `backend.api` -> `anubis.api`
- Update imports mechanically.
- Run tests after each package move.

### Phase 5: Production Hardening

- Replace FastAPI event decorators with lifespan.
- Add real provider configuration for OpenAI/Anthropic only if they are product requirements.
- Add Playwright or equivalent UI navigation tests.
- Add OS-level sandboxing for terminal execution.
- Add deployment health, metrics, and smoke-test scripts.

## Verification

Commands run after simplification:

- `python3 -m anubis.cli.main --help`
- `.venv/bin/python - <<'PY' ... from backend.main import app ...`
- `npm run build`
- `.venv/bin/python -m pytest tests/test_terminal_service.py tests/test_anubis_cli_terminal.py tests/test_cli_mvp.py tests/test_backend_desktop_api.py -q`
- `.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8011`
- HTTP checks:
  - `GET /health`
  - `GET /health/ready`

Results:

- CLI help passed.
- Backend import passed.
- Frontend production build passed.
- Focused tests passed: `27 passed`.
- Direct backend startup passed.
- Direct backend shutdown passed cleanly.

## CTO Conclusion

The repository is better after this pass because it has fewer false abstractions and fewer duplicate frontend roots. It is not production-grade yet. The next big win is not adding architecture; it is deleting or merging duplicate agent systems and route families until each capability has one owner, one entrypoint, and one test story.
