# ANUBIS DUPLICATION REPORT

> [!CAUTION]
> This codebase has **critical systemic duplication** across nearly every subsystem. At least 11 categories of duplicate functionality exist, many with 3–4 competing implementations. This is the primary source of architectural fragility, import confusion, and wasted maintenance effort.

---

## 1. CLI Systems — 4 Competing Implementations

| System | Location | Lines | Status | Verdict |
|--------|----------|-------|--------|---------|
| **Root CLI shim** | [anubis_cli.py](file:///home/fatsio/AI/Anubis/anubis_cli.py) | 9 | Thin redirect → `anubis.cli.main` | **KEEP** (entrypoint only) |
| **Loader bridge** | [anubis_cli_loader.py](file:///home/fatsio/AI/Anubis/anubis_cli_loader.py) | 24 | `importlib` hack to load `anubis-cli/` modules | **REMOVE** |
| **cli/ package** | [cli/](file:///home/fatsio/AI/Anubis/cli) (6 files) | ~130 | Proxy shim that re-exports from `anubis_cli_loader` and `anubis.core.router` | **REMOVE** |
| **anubis-cli/ standalone** | [anubis-cli/](file:///home/fatsio/AI/Anubis/anubis-cli) (24 files) | ~800 | Full CLI with own config, router, agent, dispatcher, commands | **MERGE best parts → anubis/cli** |
| **anubis/cli/ package** | [anubis/cli/](file:///home/fatsio/AI/Anubis/anubis/cli) (12 files) | ~400 | Production-grade: session runtime, themed output, loop, prompt, formatter | **KEEP** (canonical) |

### Analysis

- `cli/anubis.py` uses `anubis_cli_loader.py` to dynamically load `anubis-cli/core/agent.py` via `importlib` — a fragile hack that bypasses normal Python imports.
- `anubis/cli/main.py` also uses `anubis_cli_loader` to load from `anubis-cli/main.py`.
- `anubis-cli/` has its own `config.py`, `router.py`, `registry.py`, and domain-specific commands (CVE, OSINT, bugbounty, graph) that don't exist elsewhere.
- `anubis/cli/` is the cleanest: proper session management, `CliRouter`, `TerminalRenderer`, themed output.

### Merge Strategy

1. Move unique `anubis-cli/commands/` (CVE, OSINT, bugbounty, defense, graph, tools) → `anubis/cli/commands/`
2. Delete `cli/`, `anubis_cli_loader.py`, `anubis-cli/`
3. `anubis_cli.py` becomes a direct import of `anubis.cli.main:main`

---

## 2. Agent Systems — 2 Competing Architectures

| System | Location | Lines | Purpose | Verdict |
|--------|----------|-------|---------|---------|
| **agent/ (monolith)** | [agent/](file:///home/fatsio/AI/Anubis/agent) (18 files) | ~4,000+ | Full state-machine loop, multi-agent, orchestrator, planner, coder, reviewer, tester, debugger | **KEEP** (production runtime) |
| **anubis/distributed/** | [anubis/distributed/](file:///home/fatsio/AI/Anubis/anubis/distributed) (50+ files) | ~5,000+ | DAG-based distributed orchestrator with contracts, registries, event buses, SOC engines, attack generators | **PARTIALLY KEEP** |

### Analysis

- `agent/` is the **live production system**: `agent/loop.py` (2741 lines) is the actual autonomous agent state machine. It drives all CLI and API agent runs via `runtime/agent_runner.py`.
- `anubis/distributed/` is a **parallel universe**: a clean, contract-based distributed architecture (`DistributedOrchestrator`, `PlannerAgent`, `ReviewerAgent`, `ExecutorAgent`) with proper dependency injection. But it's **not wired to any entrypoint**.
- The two systems duplicate: orchestrator, planner, reviewer, executor, event bus, state machine, rollback.
- The `anubis/distributed/` system is architecturally superior (frozen dataclasses, protocol-based contracts, proper separation of concerns) but incomplete (no LLM integration, no tool execution).

### Merge Strategy

1. **Keep `agent/` as the runtime** — it works, it's wired, it has LLM integration.
2. **Backport the superior contracts** from `anubis/distributed/contracts.py`, `planning_schema.py`, `validation_engine.py` into `agent/`.
3. **Remove the security-specific modules** from `anubis/distributed/` (SOC, attack, defense, exploit, threat intel) — they belong in a separate `security/` package if ever needed.
4. **Remove empty/stub files**: `anubis/orchestration/engine.py` is 0 lines.

---

## 3. Router Systems — 11 Router Files

| Router | Location | Purpose | Verdict |
|--------|----------|---------|---------|
| `anubis/core/router.py` | Core | `CommandRouter` + `ParsedCommand` — canonical command routing | **KEEP** |
| `anubis/cli/router.py` | CLI | `CliRouter` wrapping `CommandRouter` with formatting | **KEEP** |
| `runtime/router.py` | Runtime | `route_agent_action()` — classifies LLM actions (plan/tool/final) | **KEEP** |
| `cli/router.py` | Legacy | 4-line re-export of `anubis.core.router` | **REMOVE** |
| `anubis-cli/router.py` | Standalone | Duplicate standalone router | **REMOVE** |
| `anubis-cli/core/router.py` | Standalone | Another duplicate router | **REMOVE** |
| `rag/router.py` | RAG | 1 line (empty) | **REMOVE** |
| `rag/shared/query_router.py` | RAG | `RagRouter` — domain routing for multi-RAG queries | **KEEP** |
| `anubis/memory/router.py` | Memory | Memory-specific routing | **REVIEW** |
| `anubis/tools/tool_router.py` | Tools | Tool dispatch routing | **REVIEW** |
| `anubis/models/router/` | Models | Model routing interfaces | **REVIEW** |

### Merge Strategy

- Delete all proxy/empty routers (`cli/router.py`, `anubis-cli/router.py`, `anubis-cli/core/router.py`, `rag/router.py`)
- Keep the 3 canonical routers: `anubis/core/router.py`, `anubis/cli/router.py`, `runtime/router.py`

---

## 4. Planner Systems — 3 Implementations

| System | Location | Lines | Quality | Verdict |
|--------|----------|-------|---------|---------|
| `agent/planner.py` | Root agent | 18 | **Stub** — returns 1 hardcoded step | **REMOVE** |
| `agent/orchestrator_agent.py` | Root agent | 367 | Full priority plan builder with dependency graphs, parallel batches, critical path analysis | **KEEP** |
| `anubis/distributed/planner_agent.py` | Distributed | 119 | Clean `PlannerAgent` class with DAG validation, work-item decomposition | **MERGE into agent/** |

### Analysis

- `agent/planner.py` is a 18-line placeholder that always returns `[{"step": 1, "goal": task, "tool_hint": "read_file"}]`. Dead code.
- `agent/orchestrator_agent.py` has the real planning: `build_priority_plan()`, `build_parallel_batches()`, dependency graph construction.
- `anubis/distributed/planner_agent.py` has cleaner architecture (frozen dataclasses, `ExecutionPlan`, `PlanStep`, `DependencyResolver`) but isn't wired.

### Merge Strategy

1. Delete `agent/planner.py` stub
2. Keep `agent/orchestrator_agent.py` as canonical planner
3. Adopt `ExecutionPlan`/`PlanStep` schemas from `anubis/distributed/planning_schema.py`

---

## 5. RAG Systems — 3 Parallel Implementations

| System | Location | Files | Purpose | Verdict |
|--------|----------|-------|---------|---------|
| **rag/ multi-domain** | [rag/](file:///home/fatsio/AI/Anubis/rag) | 73 | Full multi-domain RAG: OSINT, CVE, bugbounty, dev, defense, threat actors, graph (Neo4j), memory, tools | **KEEP** (canonical) |
| **rag_exploitdb/** | [rag_exploitdb/](file:///home/fatsio/AI/Anubis/rag_exploitdb) | 6 | Narrow ExploitDB-specific RAG | **MERGE → rag/discovery/** |
| **retrieval/** | [retrieval/](file:///home/fatsio/AI/Anubis/retrieval) | 13 | `HybridRetriever` with Qdrant + local vector + keyword fusion | **KEEP as retrieval layer** |

### Analysis

- `main.py` (root) is actually an `AnubisRagSystem` — the **main entrypoint** for RAG queries and ingestion via `rag/shared/`.
- `rag/shared/backend_legacy/` contains 6 legacy files (chunker, embedder, indexer, obsidian_memory, qdrant_store, retriever) duplicating functionality now in `retrieval/` and `storage/`.
- `rag_exploitdb/` is a narrow ExploitDB indexer that duplicates patterns from `rag/discovery/`.
- `retrieval/hybrid.py` duplicates vector search logic from `memory/hermes.py` (`_local_vector_search`).

### Merge Strategy

1. Delete `rag/shared/backend_legacy/` (superseded by `retrieval/` and `storage/`)
2. Merge `rag_exploitdb/` → `rag/discovery/` or `rag/tools/`
3. `retrieval/` stays as the unified retrieval layer consumed by `rag/` and `memory/`

---

## 6. API Layers — 2 Duplicate HTTP Servers

| System | Location | Lines | Framework | Verdict |
|--------|----------|-------|-----------|---------|
| `app/main.py` | [app/main.py](file:///home/fatsio/AI/Anubis/app/main.py) | 660 | **FastAPI** — full-featured: OpenAI compat, RAG, crawl, vault, intelligence, cache, Qdrant, metrics, background jobs | **KEEP** |
| `api/openai_server.py` | [api/openai_server.py](file:///home/fatsio/AI/Anubis/api/openai_server.py) | 431 | **stdlib `http.server`** — bare-bones OpenAI-compatible API | **REMOVE** |

### Analysis

These two servers expose **identical OpenAI-compatible endpoints** (`/v1/chat/completions`, `/v1/models`, `/v1/agent/stream`). They share:
- Same streaming logic (progress queues, worker threads, SSE formatting)
- Same response shapes (`ChatCompletionResponse`)
- Same auth checking (`API_KEY`)
- Both call `runtime.agent_runner.run_agent_loop`

`app/main.py` is strictly superior: FastAPI, CORS, async, typed Pydantic models, plus 15+ additional endpoints (RAG, vault, crawl, intelligence, monitoring).

`api/openai_server.py` uses `BaseHTTPRequestHandler` — no async, no middleware, no validation.

### Merge Strategy

1. Delete `api/openai_server.py` entirely
2. Delete `api/routes/` directory
3. If a zero-dependency fallback is needed, extract a thin module from `app/main.py`

---

## 7. LLM Adapters — 2 Ollama Clients

| System | Location | Lines | Features | Verdict |
|--------|----------|-------|----------|---------|
| `llm/ollama.py` | [llm/ollama.py](file:///home/fatsio/AI/Anubis/llm/ollama.py) | 202 | `requests`-based: `call_llm`, `call_chat`, `call_generate`, `stream_chat` with retries, fallback model, keep-alive | **KEEP** |
| `anubis/llm/ollama.py` | [anubis/llm/ollama.py](file:///home/fatsio/AI/Anubis/anubis/llm/ollama.py) | 75 | `urllib`-based: `OllamaClient` + `OllamaRouter` (intent-based model routing) | **MERGE router → llm/** |

### Analysis

- `llm/ollama.py` is the **production client** used by `runtime/llm_agents.py` and the entire agent pipeline. Full retry logic, fallback model support, streaming.
- `anubis/llm/ollama.py` has a useful `OllamaRouter` (routes prompts to code/fast/review models) but uses `urllib` instead of `requests` and lacks retry/fallback.

### Merge Strategy

1. Move `OllamaRouter` concept into `llm/ollama.py` or `llm/router.py`
2. Delete `anubis/llm/` package

---

## 8. Memory / Vector Store — 5 Competing Systems

| System | Location | Lines | Backend | Verdict |
|--------|----------|-------|---------|---------|
| `memory/hermes.py` | [memory/hermes.py](file:///home/fatsio/AI/Anubis/memory/hermes.py) | 852 | JSON file + Obsidian notes + local vector + Qdrant mirror | **KEEP** (production Hermes memory) |
| `memory/vector.py` | [memory/vector.py](file:///home/fatsio/AI/Anubis/memory/vector.py) | ~200 | Local JSON vector store (`state/vector_store.json`) | **KEEP** (used by hermes.py) |
| `anubis/memory/service.py` | [anubis/memory/service.py](file:///home/fatsio/AI/Anubis/anubis/memory/service.py) | 174 | `UnifiedMemoryService` — collection-aware, protocol-based | **KEEP** (next-gen API) |
| `anubis/memory/store.py` | [anubis/memory/store.py](file:///home/fatsio/AI/Anubis/anubis/memory/store.py) | 204 | `InMemoryMemoryStore` + `QdrantMemoryStore` + `MemoryEmbedder` | **KEEP** (clean adapters) |
| `storage/qdrant.py` | [storage/qdrant.py](file:///home/fatsio/AI/Anubis/storage/qdrant.py) | 272 | `QdrantStore` — raw HTTP Qdrant adapter | **MERGE with anubis/memory/store.py** |

### Analysis

This is the worst duplication cluster. **5 separate systems** all doing vector storage and retrieval:

1. `memory/hermes.py` uses raw `requests` against Qdrant HTTP API **and** local JSON files
2. `memory/vector.py` has its own JSON-based vector store with cosine similarity
3. `anubis/memory/store.py` has clean `MemoryVectorStore` protocol with `InMemoryMemoryStore` and `QdrantMemoryStore` adapters using `qdrant-client`
4. `storage/qdrant.py` has a full `QdrantStore` using raw `requests` (duplicates hermes.py's Qdrant code)
5. `rag/shared/qdrant_client.py` has yet another `QdrantVectorStore` used by the RAG pipeline

**Three separate Qdrant clients** exist: `memory/hermes.py` (raw HTTP), `storage/qdrant.py` (raw HTTP), `anubis/memory/store.py` (`qdrant-client` library).

### Merge Strategy

1. `anubis/memory/store.py` becomes the canonical vector store interface (it's the cleanest)
2. `storage/qdrant.py` merges into `anubis/memory/store.py` (add the health/scroll/bulk methods)
3. `memory/hermes.py` refactors to use `anubis/memory/service.py` for vector operations
4. Delete raw Qdrant HTTP calls from `memory/hermes.py`

---

## 9. Configuration Systems — 3 Config Sources

| System | Location | Lines | Scope | Verdict |
|--------|----------|-------|-------|---------|
| `config.py` | [config.py](file:///home/fatsio/AI/Anubis/config.py) | 173 | **Global** — 60+ settings: LLM, memory, API, agent, git, embedding | **KEEP** (canonical) |
| `anubis-cli/core/config.py` | [anubis-cli/core/config.py](file:///home/fatsio/AI/Anubis/anubis-cli/core/config.py) | 20 | CLI-specific subset: `CliConfig` dataclass | **REMOVE** (merge into config.py) |
| `rag/shared/config.py` | [rag/shared/config.py](file:///home/fatsio/AI/Anubis/rag/shared/config.py) | 26 | RAG-specific: `RouterConfig` with thresholds, collection prefix | **REMOVE** (merge into config.py) |

### Analysis

Three separate config systems reading overlapping env vars:
- `config.py`: `QDRANT_URL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `anubis-cli/core/config.py`: `QDRANT_URL`, `OLLAMA_BASE_URL` (different var names: `ANUBIS_LLM_MODEL`)
- `rag/shared/config.py`: `ANUBIS_QDRANT_URL` (yet another env var name for the same Qdrant URL)

### Merge Strategy

1. Consolidate all settings into `config.py`
2. Standardize env var names (e.g., always `QDRANT_URL`, never `ANUBIS_QDRANT_URL`)
3. Delete satellite configs

---

## 10. Tool Systems — 2 Parallel Registries

| System | Location | Files | Purpose | Verdict |
|--------|----------|-------|---------|---------|
| `tools/` | [tools/](file:///home/fatsio/AI/Anubis/tools) | 14 | Production tools: filesystem, terminal, git, repo, OSINT, sandbox, hermes, vector memory, dynamic tools, autonomous developer | **KEEP** |
| `anubis/tools/` | [anubis/tools/](file:///home/fatsio/AI/Anubis/anubis/tools) | 22 | Next-gen tool system: `ToolRegistry`, `ToolRouter`, `ToolEngine`, interfaces, validation, session tools, base classes | **KEEP** (better architecture) |

### Analysis

- `tools/` is the **live production tool set** — called by `agent/loop.py` via `executor/tool_executor.py`.
- `anubis/tools/` has superior architecture (registry pattern, validation, error hierarchy, protocol interfaces) but isn't fully wired.
- Specific duplicates: `tools/filesystem.py` vs `anubis/tools/filesystem.py` vs `anubis/tools/filesystem_tool.py` vs `anubis/tools/filesystem/tools.py` — **4 filesystem tool implementations**.
- `tools/sandbox.py` vs `anubis/tools/sandbox.py` — 2 sandbox implementations.

### Merge Strategy

1. Adopt `anubis/tools/` registry/engine architecture as canonical
2. Migrate `tools/*.py` implementations to use `anubis/tools/` base classes
3. Consolidate filesystem tools into one (`anubis/tools/filesystem/tools.py`)
4. Delete redundant files

---

## 11. Orchestration — 3 Overlapping Systems

| System | Location | Files | Status | Verdict |
|--------|----------|-------|--------|---------|
| `agent/orchestrator_agent.py` | [agent/orchestrator_agent.py](file:///home/fatsio/AI/Anubis/agent/orchestrator_agent.py) | 1 (367 lines) | **Active** — wired into `agent/loop.py` | **KEEP** |
| `anubis/orchestration/` | [anubis/orchestration/](file:///home/fatsio/AI/Anubis/anubis/orchestration) | 9 files | **Mostly empty** — `engine.py` is 0 lines | **REMOVE** |
| `anubis/distributed/orchestrator.py` | [anubis/distributed/orchestrator.py](file:///home/fatsio/AI/Anubis/anubis/distributed/orchestrator.py) | 1 (231 lines) | **Clean but unwired** | **MERGE contracts** |

### Analysis

- `agent/orchestrator_agent.py` is the live orchestrator — manages priorities, assignments, retries, parallel batches
- `anubis/orchestration/` has 9 files but `engine.py` is completely empty. Stubs and aspirational code
- `anubis/distributed/orchestrator.py` (`DistributedOrchestrator`) has proper event bus, registry, state management — architecturally superior but not connected

### Merge Strategy

1. Delete `anubis/orchestration/` (empty/stub)
2. Backport `DistributedOrchestrator` patterns into `agent/orchestrator_agent.py` over time

---

## Summary: Deduplication Impact

```
┌──────────────────────┬────────────┬─────────────┬──────────────┐
│ Category             │ Current    │ After Merge  │ Files Saved  │
├──────────────────────┼────────────┼─────────────┼──────────────┤
│ CLI systems          │ 4          │ 1            │ ~30 files    │
│ Agent architectures  │ 2          │ 1            │ ~40 files    │
│ Router files         │ 11         │ 5            │ 6 files      │
│ Planner systems      │ 3          │ 1            │ 2 files      │
│ RAG implementations  │ 3          │ 2            │ ~12 files    │
│ API servers          │ 2          │ 1            │ ~3 files     │
│ LLM adapters         │ 2          │ 1            │ 2 files      │
│ Memory/vector stores │ 5          │ 2            │ ~4 files     │
│ Config systems       │ 3          │ 1            │ 2 files      │
│ Tool registries      │ 2          │ 1            │ ~10 files    │
│ Orchestration        │ 3          │ 1            │ ~10 files    │
├──────────────────────┼────────────┼─────────────┼──────────────┤
│ TOTAL                │ 40 systems │ 17 systems   │ ~120 files   │
└──────────────────────┴────────────┴─────────────┴──────────────┘
```

---

## Recommended Consolidation Plan

### Phase 1 — Zero-Risk Cleanup (Day 1)
- [ ] Delete `api/openai_server.py` + `api/routes/` (superseded by `app/main.py`)
- [ ] Delete `agent/planner.py` stub (18 lines of dead code)
- [ ] Delete `rag/router.py` (1 empty line)
- [ ] Delete `rag/shared/backend_legacy/` (6 files, superseded)
- [ ] Delete `anubis/orchestration/engine.py` (0 lines)
- [ ] Delete `cli/router.py` (4-line proxy)

### Phase 2 — CLI Consolidation (Day 2-3)
- [ ] Move `anubis-cli/commands/` → `anubis/cli/commands/`
- [ ] Rewrite `anubis_cli.py` to directly import `anubis.cli.main:main`
- [ ] Delete `anubis_cli_loader.py`, `cli/`, `anubis-cli/`

### Phase 3 — Config & LLM Unification (Day 3-4)
- [ ] Merge `rag/shared/config.py` and `anubis-cli/core/config.py` into `config.py`
- [ ] Standardize env var names
- [ ] Merge `OllamaRouter` from `anubis/llm/ollama.py` into `llm/ollama.py`
- [ ] Delete `anubis/llm/`

### Phase 4 — Memory/Vector Consolidation (Day 5-7)
- [ ] Adopt `anubis/memory/store.py` as canonical vector store protocol
- [ ] Merge `storage/qdrant.py` health/scroll features into it
- [ ] Refactor `memory/hermes.py` to use unified store instead of raw HTTP
- [ ] Merge `rag_exploitdb/` into `rag/discovery/`

### Phase 5 — Tool & Agent Architecture (Week 2)
- [ ] Consolidate filesystem tools (4 → 1)
- [ ] Adopt `anubis/tools/` registry pattern as canonical
- [ ] Backport distributed contracts into `agent/`
- [ ] Archive `anubis/distributed/` security modules

> [!IMPORTANT]
> Each phase should be a separate Git branch with full test validation before merge. The `agent/loop.py` (2741 lines) should NOT be touched until all surrounding duplication is resolved — it's the beating heart of the system.
