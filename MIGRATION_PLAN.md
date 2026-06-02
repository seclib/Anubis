# MIGRATION PLAN

Strategic decision: Anubis is terminal-first. The core product is the autonomous agent running in the terminal, grounded by Obsidian files and Qdrant memory, with controlled tool execution.

The migration goal is to simplify the repository, preserve the working terminal agent, merge the best RAG/Obsidian/Qdrant pieces, and retire Desktop/Tauri/React.

## 1. Repository Audit Summary

### Required For Terminal-First Anubis

- Terminal agent:
  - `cli/`
  - `anubis_cli.py`
  - `runtime/`
  - root `agent/`
  - `tools/`
  - `executor/`

- RAG and Qdrant:
  - `backend/rag/`
  - selected `retrieval/`
  - selected `storage/qdrant.py`
  - selected `storage/keyword_index.py`

- Memory:
  - `vault/`
  - selected `memory/` for session state only
  - `backend/rag/qdrant_store.py`
  - `backend/rag/retriever.py`

- Obsidian integration:
  - `backend/vault/`
  - `backend/watcher/`
  - `scripts/ingest_obsidian.py`
  - `scripts/watch_obsidian.py`
  - optional `rag-system/obsidian-plugin/`

- Autonomous agents:
  - root `agent/`
  - `backend/agent/`
  - `runtime/agent_runner.py`
  - `runtime/llm_agents.py`
  - `runtime/streaming.py`

- Sandbox execution:
  - `tools/sandbox.py`
  - `backend/tools/sandbox.py`
  - selected `anubis/services/tools/src/anubis_tools/sandbox/`

- API, secondary/headless:
  - `backend/main.py`
  - `backend/api/routes/production.py`
  - `backend/api/routes/health.py`

### Obsolete Or Non-Strategic

- Desktop/Tauri/React:
  - `desktop/`
  - `anubis/apps/desktop/`
  - `Anubis.desktop`
  - `launcher/`
  - desktop launch/install scripts

- Frontend-only systems:
  - `frontend/`
  - React skill graph/dashboard APIs
  - desktop docs and packaging

- Abandoned duplicate service architectures:
  - `anubis/services/*`
  - `anubis/packages/*`
  - `anubis/kernel/`
  - root `app/`, `api/`, `services/`, `workers/` after backend consolidation
  - Node `rag-system/src/` after plugin retargeting

## 2. Proposed New Architecture

Target structure:

```text
anubis/
├── agent/
│   ├── loop.py
│   ├── planner.py
│   ├── executor.py
│   ├── critic.py
│   ├── roles.py
│   ├── prompts.py
│   ├── streaming.py
│   └── skills.py
├── memory/
│   ├── store.py
│   ├── session.py
│   ├── consolidation.py
│   └── schemas.py
├── rag/
│   ├── chunker.py
│   ├── embedder.py
│   ├── qdrant.py
│   ├── retriever.py
│   ├── hybrid.py
│   ├── context.py
│   └── safety.py
├── obsidian/
│   ├── vault.py
│   ├── markdown.py
│   ├── watcher.py
│   ├── sync.py
│   └── plugin_api.py
├── sandbox/
│   ├── executor.py
│   ├── permissions.py
│   ├── audit.py
│   └── schemas.py
├── api/
│   ├── app.py
│   ├── routes.py
│   └── schemas.py
├── config/
│   ├── settings.py
│   ├── paths.py
│   └── logging.py
├── terminal/
│   ├── app.py
│   ├── commands.py
│   ├── panels.py
│   ├── renderer.py
│   ├── palette.py
│   └── theme.py
├── tests/
└── docs/
```

If we want to keep the exact requested top-level shape, fold `terminal/` into `agent/` or keep the existing `cli/` outside until the migration completes:

```text
anubis/
├── agent/
├── memory/
├── rag/
├── obsidian/
├── sandbox/
├── api/
├── config/
├── tests/
└── docs/
```

Recommended practical transitional structure:

```text
anubis_core/
├── agent/
├── memory/
├── rag/
├── obsidian/
├── sandbox/
├── api/
├── config/
└── terminal/
tests/
docs/
vault/
scripts/
infra/
```

Reason: the repository already has an `anubis/` experimental monorepo. Rename or remove that old folder before claiming `anubis/` as the canonical package.

## 3. Migration Steps

### Phase 0: Freeze Desktop Work

- Stop adding features to:
  - `desktop/`
  - `anubis/apps/desktop/`
  - Tauri launchers
  - React dashboards
  - Vite build systems
- Update docs to mark desktop as deprecated.
- Remove desktop build from default checks.

### Phase 1: Declare The Canonical Runtime

- Make terminal command the primary entrypoint:
  - current: `anubis_cli.py`
  - target: `anubis`
- Make backend API secondary:
  - current best app: `backend.main:app`
  - target: `anubis.api.app:create_app`
- Update `Makefile`:
  - `make anubis`
  - `make test`
  - `make qdrant`
  - `make sync`
  - `make api`
  - remove `make desktop`.

### Phase 2: Unify Agent Systems

- Compare root `agent/` and `backend/agent/`.
- Keep terminal-proven behavior from root `agent/`.
- Keep simpler planner/executor/critic implementation from `backend/agent/multi_agent.py`.
- Produce one loop:
  - retrieve memory
  - plan
  - execute controlled tools
  - critique
  - retry if needed
  - write trace to Obsidian
  - update Qdrant
- Move specialist roles behind optional configuration.
- Remove duplicate agent packages after tests pass.

### Phase 3: Unify Memory And RAG

- Make Obsidian vault the only durable truth.
- Make Qdrant the only vector memory.
- Keep local JSON only for ephemeral session state.
- Start from `backend/rag/` as the simplest Qdrant layer.
- Merge useful pieces from `retrieval/`:
  - confidence scoring
  - query planning
  - context building
  - hybrid keyword/vector retrieval
- Merge safety pieces from `anubis/services/rag/security/`.
- Delete parallel `rag/`, `retrieval/`, `knowledge/`, and `storage/` only after replacement tests pass.

### Phase 4: Unify Sandbox And Tools

- Merge `tools/sandbox.py`, `backend/tools/sandbox.py`, and useful `anubis/services/tools` ideas.
- Define one tool execution contract:
  - command
  - args
  - cwd
  - permission class
  - timeout
  - network allowed
  - audit log entry
- Keep shell/network/file writes explicit and logged.
- Make terminal display tool execution in real time.

### Phase 5: Obsidian Integration

- Keep filesystem watcher as the default sync path.
- Keep manual sync command:
  - terminal: `/sync`
  - API: `POST /sync`
- Retarget Obsidian plugin only if useful:
  - from Node service on `8787`
  - to terminal/FastAPI backend on `8000`
- Store agent traces in:
  - `vault/agent-runs/`
- Store durable skills in:
  - `vault/skills/`
- Store consolidated memories in:
  - `vault/memories/`

### Phase 6: Retire Desktop And Duplicates

- Delete or archive desktop code.
- Remove GUI dependencies.
- Delete generated artifacts.
- Remove duplicate service monorepo after salvaging useful code.
- Remove legacy root API/service stacks after canonical terminal/API tests pass.

## 4. Terminal-First UX Proposal

The terminal should feel like a command center for an autonomous agent, not a plain chatbot.

### Interaction Modes

- `anubis`
  - starts interactive terminal session.

- `anubis ask "task"`
  - one-shot task with streaming output.

- `anubis run "objective"`
  - autonomous loop with planner/executor/critic.

- `anubis sync`
  - ingest Obsidian vault into Qdrant.

- `anubis memory "query"`
  - inspect retrieved memory.

- `anubis skills`
  - list, inspect, and generate skills.

- `anubis status`
  - show Qdrant, vault, model, watcher, sandbox, and last run.

### Modern Terminal UI

Use `rich` first. Consider `textual` only if the simple Rich UI becomes insufficient.

Default layout:

```text
┌ Anubis ─────────────────────────────────────────────────────────────┐
│ mode: autonomous  model: qwen2.5-coder  qdrant: ready  vault: live │
├ Task ───────────────────────────────────────────────────────────────┤
│ Build/refactor/fix user objective                                  │
├ Plan ───────────────┬ Memory ───────────────┬ Skills ──────────────┤
│ 1. inspect          │ notes/foo.md 0.82     │ docker_debug         │
│ 2. patch            │ notes/bar.md 0.77     │ repo_triage          │
│ 3. test             │                       │                      │
├ Activity ───────────────────────────────────────────────────────────┤
│ [planner] retrieved 6 chunks                                        │
│ [executor] read backend/rag/indexer.py                              │
│ [sandbox] pytest tests/test_agent_loop.py OK                        │
│ [critic] approved                                                  │
└ Response ───────────────────────────────────────────────────────────┘
```

### Panels

- Task panel:
  - current objective
  - loop iteration
  - accepted/retry state

- Plan panel:
  - planner steps
  - status per step
  - failed step highlighting

- Memory panel:
  - top retrieved chunks
  - path, heading, score
  - quick open path in editor

- Skill panel:
  - matched skills
  - generated skill proposals
  - approval status

- Tool panel:
  - command/file/network operations
  - permission class
  - stdout/stderr summary

- Activity log:
  - streaming agent events
  - watcher sync events
  - memory writes
  - critic decisions

### Command Palette

Support slash commands:

- `/ask`
- `/run`
- `/sync`
- `/memory`
- `/skills`
- `/status`
- `/model`
- `/vault`
- `/watch`
- `/logs`
- `/approve`
- `/deny`
- `/quit`

### Streaming Output

- Stream LLM tokens where possible.
- Stream tool events immediately.
- Show retrieved memory before final answer.
- Show critic result and retry reason.
- Keep full trace in Obsidian, concise output in terminal.

### Terminal UX Principles

- Never hide tool execution.
- Always show memory retrieval.
- Make failures actionable.
- Prefer keyboard commands.
- Keep UI readable over decorative.
- Use plain files for traces and history.

## 5. Future Roadmap

### 1. Agent Intelligence

- One canonical planner/executor/critic loop.
- Memory retrieval before every reasoning step.
- Strict critic with retry budget.
- Specialist roles as optional modules, not mandatory architecture.
- Better task decomposition and progress recovery.
- Trace every agent decision to Markdown.

### 2. RAG Quality

- Hybrid Qdrant + keyword retrieval.
- Better Markdown chunking:
  - headings
  - backlinks
  - tags
  - frontmatter
  - code blocks
- Query rewriting.
- Confidence scoring.
- Context compression before answer generation.
- Memory poisoning and prompt-injection filters.

### 3. Obsidian Integration

- Watcher-first sync.
- Manual terminal sync.
- Agent run notes.
- Skill notes.
- Memory consolidation notes.
- Optional plugin only for commands inside Obsidian.
- Do not require GUI app.

### 4. Skill Generation

- Detect repeated task patterns.
- Generate Markdown skills.
- Critic validates skills before saving.
- Skills are searchable through Qdrant.
- Terminal can inspect, approve, reject, and edit generated skills.

### 5. Autonomous Planning

- Multi-step execution with visible plan.
- Tool-use permissions.
- Checkpoint state after each step.
- Resume failed tasks.
- Critic-guided retry.
- Post-run summary and memory update.

### 6. Sandbox Security

- One permission model.
- No shell by default for high-risk actions.
- Explicit allowlist.
- Timeouts.
- Working-directory jail.
- Audit log in JSONL.
- Terminal approval for dangerous operations.
- Optional dry-run mode.

### 7. Memory Consolidation

- Separate ephemeral session state from durable memory.
- Durable memory lives in Obsidian.
- Embeddings live in Qdrant.
- Periodic deduplication.
- Memory decay/archival.
- Daily or topic-based summary notes.
- Agent learns from previous runs without storing noise.

## 6. Success Criteria

The migration is successful when:

- `anubis` terminal command is the primary interface.
- Qdrant sync works from terminal.
- Obsidian watcher updates memory in real time.
- Agent always retrieves memory before reasoning.
- Agent can execute controlled tools with visible logs.
- Skills are Markdown files and searchable.
- Desktop code is no longer in default build/test/dev flows.
- There is one canonical agent loop.
- There is one canonical RAG/Qdrant layer.
- There is one canonical sandbox.
- Tests pass without React, Tauri, Vite, or desktop dependencies.

