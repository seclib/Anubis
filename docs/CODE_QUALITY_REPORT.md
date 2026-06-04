# Code Quality Report

Date: 2026-06-04

Scope: source-level quality pass across the repository, excluding generated/dependency/runtime artifacts where practical (`.git`, `.venv`, `node_modules`, `dist`, `.next`, `target`, `state`, `__pycache__`). The repository already had extensive uncommitted changes, so fixes were limited to high-confidence safe changes that would not overwrite active user work.

## Summary

Reviewed the project using:

- Python AST syntax scan across 669 Python files.
- Source inventory across 743 source-like files.
- Targeted broad-exception / placeholder scan.
- Targeted import sweep for the new canonical architecture layer.
- Python compile verification for canonical architecture modules.
- CLI/API startup smoke checks.
- Frontend TypeScript/Vite production build.
- Focused Python test slice covering CLI and backend desktop API behavior.

Safe fixes applied:

- Tightened broad exception handling in the new canonical adapter layer.
- Replaced placeholder `pass` classes/stubs with explicit behavior or explicit unavailable adapters.
- Fixed a real Qdrant fallback bug that caused API note writes to fail when a local Qdrant collection had the wrong vector dimension.
- Removed duplicate embedding work in Qdrant chunk upsert.
- Kept generated `__pycache__` artifacts out of the new architecture folders after verification.

## Fix 1: New Adapter Layer Used Broad Exception Handling

### Before

Several newly added canonical adapter modules used broad `except Exception` blocks for optional compatibility imports:

- `anubis/bootstrap/settings.py`
- `anubis/application/agents/critic.py`
- `anubis/application/agents/prompt_service.py`
- `anubis/application/memory/cache_service.py`
- `anubis/application/memory/retrieval_service.py`
- `anubis/application/orchestration/worker_service.py`
- `anubis/infrastructure/cache/redis.py`
- `anubis/interfaces/api/routes/openai_compat.py`
- `anubis/interfaces/worker/jobs.py`

This was too broad. It could hide real bugs inside imported modules.

### After

Changed broad handlers to `except ImportError` where the intent is optional dependency / optional legacy-module availability.

For `openai_compat`, replaced the direct import-plus-broad-catch with `import_module()` and `getattr()` so missing `router` is handled explicitly without swallowing arbitrary runtime errors.

Impact:

- Safer failure behavior.
- Real import-time bugs are less likely to be hidden.
- Compatibility behavior is preserved for slim installs.

## Fix 2: Placeholder Classes And Empty Stubs

### Before

The new architecture layer had placeholder `pass` bodies:

- `anubis/application/orchestration/scheduler_service.py`
- `anubis/infrastructure/llm/openai.py`
- `anubis/infrastructure/llm/anthropic.py`
- `anubis/interfaces/api/errors.py`
- `anubis/interfaces/worker/jobs.py`
- `anubis/shared/errors.py`

These made the target layer look more complete than it was and provided no behavior.

### After

Changed placeholders to explicit behavior:

- `SchedulerService` now tracks registered job names and exposes `jobs()`.
- `OpenAIAdapter` and `AnthropicAdapter` now raise explicit unavailable errors until configured.
- `ApiError` and `AnubisError` now have clear class docstrings.
- `interfaces/worker/jobs.py` now explicitly imports known worker functions and exports a stable `__all__`.

Impact:

- Less ambiguous scaffolding.
- Clearer behavior for unconfigured provider adapters.
- Better onboarding for future implementation work.

## Fix 3: Qdrant Upsert Could Crash API Writes

### Before

`backend/rag/qdrant_store.py` handled Qdrant unavailability in `ensure_collection()`, but not Qdrant write/query/delete failures after the collection existed.

The focused backend API test exposed this failure:

```text
Wrong input: Vector dimension error: expected dim: 32, got 1024
```

The failure occurred during a background note reindex after writing a note. A stale local Qdrant collection with a mismatched dimension caused `client.upsert()` to raise, which escaped and failed the API request.

### After

Updated `QdrantStore` to degrade to local fallback when Qdrant upsert, delete, or query operations fail after collection setup.

Changed methods:

- `upsert_chunks`
- `delete_path`
- `search`

Impact:

- API note writes no longer fail just because local Qdrant has a stale/mismatched collection.
- Local/test environments are more robust.
- Qdrant errors are logged as warnings and fallback search remains available.

## Fix 4: Duplicate Embedding Work In Qdrant Upsert

### Before

`backend/rag/qdrant_store.py::upsert_chunks()` embedded every chunk twice:

- Once for fallback points.
- Once again for Qdrant `PointStruct` objects.

This doubled embedding cost during ingestion.

### After

The method now computes fallback points once and builds Qdrant points from the already computed vectors.

Impact:

- Lower CPU/network cost for embedding-backed ingestion.
- Less latency during vault reindexing.
- No behavior change to payloads or IDs.

## Fix 5: Generated Bytecode Artifacts From Verification

### Before

Running `compileall` created `__pycache__` directories under the new canonical architecture folders.

### After

Removed generated `__pycache__` directories after verification.

Impact:

- Keeps source tree cleaner.
- Avoids adding generated artifacts to the dirty worktree.

## Scans And Findings

### Syntax Scan

Command:

```bash
python3 - <<'PY'
import os, ast
...
PY
```

Result:

- 669 Python files scanned.
- 0 syntax errors.

### Broad Exception Scan

Result:

- 144 broad `except Exception` occurrences remain repo-wide.

Most are in legacy runtime/infrastructure boundaries such as:

- root `agent/`
- root `cli/`
- root `memory/`
- root `storage/`
- `backend/agent/`
- `backend/tools/`
- `backend/rag/`
- `app/main.py`
- `api/openai_server.py`

These were not mass-fixed because many are intentional runtime boundaries, optional dependency guards, or legacy behaviors that require tests and design migration before narrowing safely.

### New Architecture Layer Scan

Command:

```bash
rg -n "\bpass\b|except Exception|TODO|FIXME" \
  anubis/bootstrap anubis/domain anubis/ports anubis/application \
  anubis/infrastructure anubis/interfaces anubis/shared
```

Result after fixes:

- No matches.

## Verification

### Canonical CLI Startup

Command:

```bash
python3 -m anubis.interfaces.cli.main --help
```

Result:

- Passed.
- CLI help rendered.

### Canonical API Startup

Command:

```bash
.venv/bin/python - <<'PY'
from anubis.interfaces.api.app import app
from anubis.bootstrap import build_container
print(app.title, len(app.routes))
print(build_container().api_app().title)
PY
```

Result:

```text
Anubis Desktop OS API 54
Anubis Desktop OS API
```

### Canonical Architecture Compile Check

Command:

```bash
.venv/bin/python -m compileall -q \
  anubis/bootstrap anubis/domain anubis/ports anubis/application \
  anubis/infrastructure anubis/interfaces anubis/shared
```

Result:

- Passed.

### Frontend Build

Command:

```bash
npm run build
```

Result:

- Passed.
- TypeScript and Vite production build completed.

### Focused Python Tests

Command:

```bash
.venv/bin/python -m pytest \
  tests/test_anubis_cli_terminal.py \
  tests/test_cli_mvp.py \
  tests/test_backend_desktop_api.py \
  -q
```

Initial result:

- 18 passed.
- 1 failed due to Qdrant vector dimension mismatch escaping fallback.

After Qdrant fallback fix:

- 19 passed.
- 5 warnings.

Warnings observed:

- FastAPI/Starlette TestClient deprecation warning.
- FastAPI `on_event` deprecation warnings in `backend/main.py`.

## Remaining Issues Not Safely Fixed In This Pass

### Legacy Broad Exception Handling

There are still many broad exception handlers in legacy modules. Some should be narrowed, but doing so safely requires focused tests per subsystem.

Recommendation:

- Start with `backend/tools`, `backend/rag`, and `backend/agent`.
- Convert broad catches into explicit infrastructure-boundary exceptions.
- Preserve fallback behavior where external services are optional.

### Deprecated FastAPI Startup/Shutdown Hooks

`backend/main.py` still uses `@app.on_event("startup")` and `@app.on_event("shutdown")`.

Recommendation:

- Migrate to FastAPI lifespan handlers once API composition is moved fully into `anubis/interfaces/api/app.py`.

### Duplicated Architecture Still Exists

The major duplication documented in `ARCHITECTURE_AUDIT.md` and `DUPLICATION_REPORT.md` remains. This pass fixed safe quality issues but did not delete legacy duplicate systems.

Recommendation:

- Continue migration toward canonical `anubis/application`, `anubis/infrastructure`, and `anubis/interfaces`.
- Delete legacy folders only after imports and tests are migrated.

### Tool And Security Policy Still Split In Legacy Code

The canonical adapter layer is cleaner, but legacy tool execution still exists in multiple places.

Recommendation:

- Move `backend/tools/sandbox.py` fully into `anubis/infrastructure/process/sandbox.py`.
- Route all tool calls through `anubis/application/tools/tool_service.py`.

### Generated Build Output

`npm run build` writes `dist/`. It is ignored by git, but build output remains on disk.

Recommendation:

- Keep `dist/` ignored.
- CI should build from a clean checkout.

## Files Modified In This Quality Pass

- `anubis/bootstrap/settings.py`
- `anubis/application/agents/critic.py`
- `anubis/application/agents/prompt_service.py`
- `anubis/application/memory/cache_service.py`
- `anubis/application/memory/retrieval_service.py`
- `anubis/application/orchestration/scheduler_service.py`
- `anubis/application/orchestration/worker_service.py`
- `anubis/infrastructure/cache/redis.py`
- `anubis/infrastructure/llm/openai.py`
- `anubis/infrastructure/llm/anthropic.py`
- `anubis/interfaces/api/errors.py`
- `anubis/interfaces/api/routes/openai_compat.py`
- `anubis/interfaces/worker/jobs.py`
- `anubis/shared/errors.py`
- `backend/rag/qdrant_store.py`
- `CODE_QUALITY_REPORT.md`

## Before / After Summary

Before:

- New canonical adapter layer had broad catches and placeholders.
- Qdrant dimension mismatch could crash note-write API flows.
- Qdrant upsert embedded chunks twice.
- Focused backend desktop API test failed in a local stale-Qdrant environment.

After:

- New canonical adapter layer has no broad `except Exception`, `pass`, TODO, or FIXME scan hits.
- Qdrant write/query/delete failures degrade to local fallback.
- Qdrant upsert reuses computed embeddings.
- Focused Python test slice passes.
- CLI, API startup, compile check, and frontend build pass.
