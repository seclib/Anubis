# Refactor Log

Date: 2026-06-04

## Scope Applied

Applied the first production-safe architecture pass from `TARGET_ARCHITECTURE.md`.

This pass establishes the canonical package structure under `anubis/` and routes entrypoints through the target architecture without deleting active legacy code. The repository had many pre-existing uncommitted changes, including modified/deleted CLI files and MVP files, so this refactor avoided moving or deleting user-modified source files.

## Major Operation 1: Added Canonical Architecture Layers

Created the target package layers:

- `anubis/bootstrap/`
- `anubis/domain/`
- `anubis/ports/`
- `anubis/application/`
- `anubis/infrastructure/`
- `anubis/interfaces/`
- `anubis/shared/`
- `anubis/py.typed`

### Bootstrap

Added:

- `anubis/bootstrap/settings.py`
- `anubis/bootstrap/container.py`
- `anubis/bootstrap/lifecycle.py`
- `anubis/bootstrap/__init__.py`

Responsibilities added:

- Canonical typed settings.
- Central dependency container.
- Shared lifecycle hooks.

Compatibility notes:

- `settings.py` consolidates the target config surface while preserving existing environment names.
- Added legacy boolean parsing so values such as `DEBUG=release` do not break startup.

### Domain Layer

Added pure model/policy modules:

- `anubis/domain/agents/*`
- `anubis/domain/tools/*`
- `anubis/domain/memory/*`
- `anubis/domain/workspace/*`
- `anubis/domain/skills/*`
- `anubis/domain/orchestration/*`
- `anubis/domain/security/*`

Responsibilities added:

- Agent request/response models.
- Tool request/result models.
- Memory/retrieval models.
- Workspace path and note models.
- Skill models.
- Domain event and task state models.
- Security trust/redaction helpers.

### Ports Layer

Added:

- `anubis/ports/llm.py`
- `anubis/ports/embeddings.py`
- `anubis/ports/vector_store.py`
- `anubis/ports/file_store.py`
- `anubis/ports/git.py`
- `anubis/ports/process.py`
- `anubis/ports/cache.py`
- `anubis/ports/audit_log.py`
- `anubis/ports/event_bus.py`
- `anubis/ports/keyword_index.py`
- `anubis/ports/clock.py`
- `anubis/ports/secret_store.py`
- `anubis/ports/watcher.py`

Responsibilities added:

- Protocol boundaries for LLMs, embeddings, vector stores, file stores, git, process execution, cache, audit log, events, secrets, and watchers.

### Application Layer

Added compatibility application services:

- `anubis/application/agents/*`
- `anubis/application/tools/*`
- `anubis/application/memory/*`
- `anubis/application/workspace/*`
- `anubis/application/skills/*`
- `anubis/application/orchestration/*`
- `anubis/application/health/*`

Responsibilities added:

- Canonical homes for agent loop, planner, executor, verifier, critic, sessions, and prompts.
- Canonical homes for tool execution, registry, policy, and audit services.
- Canonical homes for memory ingestion, retrieval, context, compression, and cache services.
- Canonical homes for file, git, vault, skill, plugin, DSL, task, event, worker, and health services.

Compatibility adapters:

- `anubis/application/agents/loop.py` delegates to `backend.agent.core_loop.AgentLoop`.
- `anubis/application/agents/planner.py` delegates to `backend.agent.planner`.
- `anubis/application/agents/executor.py` delegates to `backend.agent.executor`.
- `anubis/application/agents/verifier.py` delegates to `backend.agent.verifier`.
- `anubis/application/tools/tool_service.py` delegates to `backend.tools.invoke_tool`.
- `anubis/application/memory/ingestion_service.py` delegates to `backend.rag.indexer.RagIndexer`.
- `anubis/application/memory/context_service.py` delegates to `backend.context.engine.ContextEngine`.
- `anubis/application/workspace/vault_service.py` delegates to `backend.vault.service.VaultService`.

### Infrastructure Layer

Added compatibility infrastructure adapters:

- `anubis/infrastructure/llm/*`
- `anubis/infrastructure/embeddings/*`
- `anubis/infrastructure/vector_store/*`
- `anubis/infrastructure/keyword_index/*`
- `anubis/infrastructure/cache/*`
- `anubis/infrastructure/filesystem/*`
- `anubis/infrastructure/process/*`
- `anubis/infrastructure/git/*`
- `anubis/infrastructure/audit/*`
- `anubis/infrastructure/secrets/*`

Responsibilities added:

- Canonical homes for model providers, embeddings, Qdrant, cache, filesystem, sandbox/process, git, audit, and secrets.

Compatibility adapters:

- `anubis/infrastructure/vector_store/qdrant.py` delegates to `backend.rag.qdrant_store.QdrantStore`.
- `anubis/infrastructure/process/sandbox.py` delegates to `backend.tools.sandbox`.
- `anubis/infrastructure/filesystem/*` delegates to backend filesystem/vault/watcher implementations.
- `anubis/infrastructure/git/cli_git.py` delegates to backend git tools.

### Interfaces Layer

Added:

- `anubis/interfaces/api/*`
- `anubis/interfaces/cli/*`
- `anubis/interfaces/worker/*`
- `anubis/interfaces/desktop_bridge/*`

Responsibilities added:

- Canonical API app factory.
- Canonical CLI entrypoint.
- Canonical worker entrypoint.
- Canonical desktop bridge namespace.

Compatibility adapters:

- `anubis/interfaces/api/app.py` returns `backend.main.app` as the default canonical API app.
- `create_app(mode="openai")` returns the legacy OpenAI-compatible `app.main.app` for parity checks.
- `anubis/interfaces/cli/main.py` delegates to existing `anubis.cli.main`.

### Shared Layer

Added:

- `anubis/shared/errors.py`
- `anubis/shared/json.py`
- `anubis/shared/logging.py`
- `anubis/shared/text.py`
- `anubis/shared/typing.py`

Responsibilities added:

- Small shared helpers for errors, JSON, logging, text normalization, and typing.

## Verification After Major Operation 1

Baseline before refactor:

```bash
python3 -m anubis.cli.main --help
```

Result:

- Passed.
- CLI help rendered.

```bash
.venv/bin/python - <<'PY'
from backend.main import app
print(app.title)
print(len(app.routes))
PY
```

Result:

- Passed.
- Output: `Anubis Desktop OS API`, `54`.

```bash
.venv/bin/python - <<'PY'
from app.main import app
print(app.title)
print(len(app.routes))
PY
```

Result:

- Passed.
- Output: `Anubis Agent API`, `26`.

Canonical checks after adding architecture layers:

```bash
python3 -m anubis.interfaces.cli.main --help
```

Result:

- Passed.
- CLI help rendered.

```bash
.venv/bin/python - <<'PY'
from anubis.interfaces.api.app import app, create_app
print(app.title)
print(len(app.routes))
print(create_app(mode='openai').title)
PY
```

Result:

- Passed after settings compatibility fix.
- Output: `Anubis Desktop OS API`, `54`, `Anubis Agent API`.

```bash
.venv/bin/python - <<'PY'
from anubis.bootstrap import build_container
container = build_container()
print(type(container).__name__)
print(container.api_app().title)
PY
```

Result:

- Passed after settings compatibility fix.
- Output: `ApplicationContainer`, `Anubis Desktop OS API`.

## Major Operation 2: Updated Packaging Entry Point

Modified:

- `pyproject.toml`
- `anubis/interfaces/cli/__init__.py`

Changes:

- Changed console script from:

```text
anubis = "anubis.cli.main:main"
```

to:

```text
anubis = "anubis.interfaces.cli.main:main"
```

- Narrowed package discovery from:

```text
["anubis*", "cli*", "backend*", "cli_mvp*"]
```

to:

```text
["anubis*", "backend*"]
```

Rationale:

- `anubis.interfaces.cli.main` is now the canonical CLI adapter.
- `backend*` remains temporarily packaged because new canonical adapters delegate to backend implementations during migration.
- Root `cli*` and `cli_mvp*` are no longer package targets.

Also removed eager import from `anubis/interfaces/cli/__init__.py` to prevent a `runpy` warning when executing `python3 -m anubis.interfaces.cli.main`.

## Verification After Major Operation 2

```bash
python3 -m anubis.interfaces.cli.main --help
```

Result:

- Passed.
- CLI help rendered with no `runpy` warning.

```bash
.venv/bin/python - <<'PY'
from anubis.interfaces.api.app import app
print(app.title)
print(len(app.routes))
PY
```

Result:

- Passed.
- Output: `Anubis Desktop OS API`, `54`.

```bash
.venv/bin/python - <<'PY'
from anubis.bootstrap import build_container
print(build_container().api_app().title)
PY
```

Result:

- Passed.
- Output: `Anubis Desktop OS API`.

## Compatibility Sweep

Ran:

```bash
.venv/bin/python - <<'PY'
modules = [
    'anubis.bootstrap',
    'anubis.application.agents.loop',
    'anubis.application.agents.planner',
    'anubis.application.agents.executor',
    'anubis.application.agents.verifier',
    'anubis.application.tools.tool_service',
    'anubis.application.memory.ingestion_service',
    'anubis.application.memory.context_service',
    'anubis.application.workspace.vault_service',
    'anubis.infrastructure.process.sandbox',
    'anubis.infrastructure.vector_store.qdrant',
    'anubis.interfaces.api.app',
    'anubis.interfaces.cli.main',
]
for module in modules:
    __import__(module)
    print('ok', module)
PY
```

Initial result:

- Failed on `anubis.application.memory.ingestion_service`.
- Cause: adapter referenced non-existent `backend.rag.indexer.VaultIndexer`.

Fix:

- Changed adapter to import `backend.rag.indexer.RagIndexer`.

Final result:

- Passed for all listed modules.

## Compile Verification

Ran:

```bash
.venv/bin/python -m compileall -q anubis/bootstrap anubis/domain anubis/ports anubis/application anubis/infrastructure anubis/interfaces anubis/shared
```

Result:

- Passed.

Cleanup:

- Removed generated `__pycache__` directories created by this compile verification under the new architecture folders.

## Final Startup Verification

Ran:

```bash
python3 -m anubis.interfaces.cli.main --help
```

Result:

- Passed.

Ran:

```bash
.venv/bin/python - <<'PY'
from anubis.interfaces.api.app import app, create_app
from anubis.bootstrap import build_container
print(app.title, len(app.routes))
print(create_app(mode='openai').title)
print(build_container().api_app().title)
PY
```

Result:

- Passed.
- Output:

```text
Anubis Desktop OS API 54
Anubis Agent API
Anubis Desktop OS API
```

## Files Modified

Modified existing files:

- `pyproject.toml`
- `anubis/interfaces/cli/__init__.py`

Added new files/folders:

- `anubis/py.typed`
- `anubis/bootstrap/`
- `anubis/domain/`
- `anubis/ports/`
- `anubis/application/`
- `anubis/infrastructure/`
- `anubis/interfaces/`
- `anubis/shared/`
- `REFACTOR_LOG.md`

Pre-existing uncommitted files from earlier work remain untouched except where explicitly listed above.

## Deferred Work

Not performed in this pass:

- Did not delete root `agent/`, `api/`, `rag/`, `tools/`, `memory/`, or `cli_mvp/`.
- Did not move `backend/` yet because canonical adapters currently preserve functionality through backend implementations.
- Did not move frontend files into `apps/desktop/`.
- Did not rewrite every legacy import across the repository.

Reason:

- The current workspace contains active uncommitted user changes and multiple runnable entrypoints. A destructive move/delete pass would risk breaking functionality and losing user work. This pass establishes the canonical architecture and entrypoints first, then leaves legacy deletion for the next migration phase once tests and imports are migrated.
