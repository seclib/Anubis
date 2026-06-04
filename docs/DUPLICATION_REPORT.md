# Duplication Report

Date: 2026-06-04

Scope: source scan of the current workspace, excluding generated/dependency/runtime folders where practical (`.git`, `.venv`, `node_modules`, `dist`, `.next`, `src-tauri/target`, `state`, `__pycache__`). No source code was modified.

## Executive Summary

The project has systemic duplication. This is not limited to a few copied helper functions; whole architectural layers exist three or four times:

- Agent loops exist in `agent/`, `backend/agent/`, `anubis/agents/`, and `anubis/core/agent_loop/`.
- Tool execution and sandboxing exist in `tools/`, `backend/tools/`, `anubis/tools/`, and parts of `anubis/distributed/`.
- Memory/RAG/Qdrant retrieval exists in `memory/`, `retrieval/`, `rag/`, `storage/`, `backend/rag/`, `backend/context/`, `anubis/memory/`, and `anubis/context/`.
- API wrappers exist in `app/main.py`, `api/openai_server.py`, `api/routes/`, and `backend/api/routes/`.
- UI exists in root `src/`, nested `anubis/src/`, and `desktop-ui/`.
- Configuration exists in `config.py`, `backend/core/config.py`, and an empty `anubis/core/config.py`.

The best consolidation path is to make `anubis/` the canonical package, keep the strongest current implementations from `backend/` where they are more complete, and delete legacy root and MVP surfaces after migration.

## 1. Duplicated Agent Loops

Files involved:

- `agent/loop.py`
- `agent/multi_agent.py`
- `backend/agent/multi_agent.py`
- `backend/agent/core_loop.py`
- `backend/agent/agent_loop.py`
- `backend/agent/loop.py`
- `anubis/core/agent_loop/loop.py`
- `anubis/agents/loop.py`
- `anubis/agents/swarm.py`

Why they overlap:

All of these model the same lifecycle: classify/plan, retrieve context, execute steps, verify or critique, retry, and return a result. Static analysis found duplicate classes named `AgentLoop`, `Planner`, `Executor`, `Plan`, `PlanStep`, `StepResult`, `ExecutionResult`, and `Critique` across these files.

Best implementation:

- Best foundation: `anubis/core/agent_loop/loop.py` plus `anubis/core/planner/planner.py`, `anubis/core/executor/executor.py`, and `anubis/core/verifier/verifier.py`.
- Best feature depth to merge in: `backend/agent/core_loop.py` and `backend/agent/multi_agent.py`, because they include memory grounding, intent classification, critique, retry behavior, and LLM fallback behavior.

Recommend deleting:

- Delete `agent/loop.py` and `agent/multi_agent.py` after any unique behavior is migrated.
- Delete `backend/agent/loop.py` and `backend/agent/agent_loop.py` if they remain thin/older variants.
- Delete `anubis/agents/loop.py` if `anubis/core/agent_loop/loop.py` becomes canonical.

Recommend merging:

- Merge memory-grounded planning and critique from `backend/agent/core_loop.py` into the canonical `anubis/core/agent_loop`.
- Merge the stricter tool-planning model from `backend/agent/planner.py` into `anubis/core/planner`.
- Keep `anubis/agents/swarm.py` only if swarm orchestration is a distinct use case; otherwise fold its agent orchestration into the canonical loop.

## 2. Duplicated Planner/Executor/Verifier Classes

Files involved:

- `agent/planner.py`
- `backend/agent/planner.py`
- `backend/agent/executor.py`
- `backend/agent/verifier.py`
- `backend/agent/multi_agent.py`
- `backend/agent/core_loop.py`
- `anubis/agents/planner.py`
- `anubis/agents/executor.py`
- `anubis/agents/verifier.py`
- `anubis/core/planner/planner.py`
- `anubis/core/executor/executor.py`
- `anubis/core/verifier/verifier.py`
- `anubis/core/*/interfaces.py`

Why they overlap:

The project defines the same business contracts multiple times: `Planner`, `Executor`, `Verifier`, `Plan`, `PlanStep`, `StepResult`, and validation logic. `backend/agent/executor.py` imports `backend.agent.verifier`, while `backend/agent/verifier.py` imports `backend.agent.executor`, creating a direct cycle.

Best implementation:

- Keep `anubis/core/*` as the canonical boundary and interface location.
- Merge `backend/agent/verifier.py` because it has stronger concrete validation for file and command results.

Recommend deleting:

- Delete duplicate `anubis/agents/planner.py`, `anubis/agents/executor.py`, and `anubis/agents/verifier.py` if they are just role wrappers.
- Delete root `agent/planner.py` after migration.
- Delete protocol duplicates inside `backend/agent/multi_agent.py` and `backend/agent/core_loop.py` once shared contracts exist.

Recommend merging:

- Move all shared dataclasses into one model module, preferably `anubis/core/types.py` or `anubis/types.py`, not both.
- Move file/command verification into one verifier service and break the executor/verifier import cycle with shared result types.

## 3. Duplicated Agent Roles

Files involved:

- `agent/coder_agent.py`
- `agent/debugger_agent.py`
- `agent/orchestrator_agent.py`
- `agent/reviewer_agent.py`
- `agent/tester_agent.py`
- `anubis/agents/critic.py`
- `anubis/agents/executor.py`
- `anubis/agents/planner.py`
- `anubis/agents/reviewer.py`
- `anubis/agents/verifier.py`
- `anubis/distributed/planner_agent.py`
- `anubis/distributed/executor_agent.py`
- `anubis/distributed/reviewer_agent.py`
- `anubis/agents/session.py`
- `backend/agent/critic.py`
- `backend/agent/planner.py`
- `backend/agent/executor.py`
- `backend/agent/verifier.py`

Why they overlap:

The same conceptual roles are implemented as root agents, backend agents, core agents, distributed agents, and session agents. For example `PlannerAgent`, `ExecutorAgent`, and `ReviewerAgent` exist in both `anubis/distributed/*` and `anubis/agents/session.py`.

Best implementation:

- Keep role definitions in `anubis/agents/roles.py` and keep execution behavior in the canonical core loop.
- Keep `anubis/distributed/*` only for truly distributed orchestration concerns.

Recommend deleting:

- Delete root `agent/*_agent.py` after unique prompts or behavior are extracted.
- Delete duplicate role implementations in `anubis/agents/session.py` if `anubis/distributed/*` or core services own them.

Recommend merging:

- Merge role prompts from `agent/prompts.py`, `anubis/agents/prompts.py`, `backend/agent/prompts.py`, and `runtime/prompts.py` into one prompt registry.
- Convert agents into configuration/strategy objects instead of separate class trees.

## 4. Duplicated Tool Execution And Sandbox Logic

Files involved:

- `backend/tools/sandbox.py`
- `tools/sandbox.py`
- `anubis/tools/sandbox.py`
- `backend/tools/filesystem.py`
- `tools/filesystem.py`
- `anubis/tools/filesystem.py`
- `anubis/tools/filesystem/tools.py`
- `backend/tools/shell.py`
- `tools/terminal.py`
- `anubis/tools/shell.py`
- `anubis/distributed/filesystem_jail.py`
- `anubis/distributed/sandbox_runtime.py`
- `anubis/distributed/permission_manager.py`
- `anubis/distributed/network_isolation.py`

Why they overlap:

All of these define variants of safe file access, command validation, shell execution, path containment, allow/deny lists, network rules, and audit logging. Identical helper bodies were found for `_command_name` in `tools/sandbox.py` and `backend/tools/sandbox.py`; path containment logic appears in several places.

Best implementation:

- Best current sandbox: `backend/tools/sandbox.py`. It has the most complete command validator, explicit `ToolRequest`, `ToolResult`, `ToolValidator`, shell-control checks, forbidden commands, network command handling, path validation, and audit output.
- Best typed tool abstraction: `anubis/tools/base.py` and `anubis/tools/filesystem/tools.py`.

Recommend deleting:

- Delete `tools/sandbox.py`, `tools/filesystem.py`, and `tools/terminal.py` after routing root callers through the canonical tool pipeline.
- Delete `anubis/tools/sandbox.py` if it remains empty/scaffold-like.
- Delete duplicate filesystem wrappers in `backend/tools/filesystem.py` or `anubis/tools/filesystem/tools.py` after choosing one canonical package location.

Recommend merging:

- Move `backend/tools/sandbox.py` into `anubis/tools/sandbox.py` or `anubis/infrastructure/local_shell`.
- Use `anubis/tools/base.py` as the common tool interface.
- Merge distributed jail/network/permission checks as policy modules used by the single sandbox pipeline, not as separate execution stacks.

## 5. Duplicated Tool Registries

Files involved:

- `backend/tools/registry.py`
- `anubis/tools/registry.py`
- `anubis/tools/tool_router.py`
- `anubis/tools/engine.py`
- `runtime/tool_registry.py`
- `cli_mvp/commands/registry.py`
- `anubis/distributed/registry.py`
- `anubis/agents/registry.py`

Why they overlap:

All implement some form of `register`, `get`, `discover`, or `route` for tools, commands, agents, or plugins. The names differ, but the responsibility is repeatedly "store callable capability by name and invoke/lookup it."

Best implementation:

- Keep `anubis/tools/registry.py` and `anubis/tools/engine.py` as the canonical tool registry/execution engine if the package is standardized.
- Keep `anubis/agents/registry.py` only for agent metadata, not tools.

Recommend deleting:

- Delete `runtime/tool_registry.py` once runtime uses `anubis.tools`.
- Delete `cli_mvp/commands/registry.py` with the MVP CLI.
- Delete overlapping registry behavior in `anubis/tools/tool_router.py` after merging routing into the tool engine.

Recommend merging:

- Create one `CapabilityRegistry` abstraction only if tools, commands, and agents truly share lifecycle behavior; otherwise keep separate names with strict ownership.

## 6. Duplicated Memory, RAG, Context, And Retrieval Logic

Files involved:

- `memory/hermes.py`
- `memory/vector.py`
- `memory/query_cache.py`
- `memory/state.py`
- `retrieval/service.py`
- `retrieval/optimized.py`
- `retrieval/hybrid.py`
- `retrieval/memory_router.py`
- `retrieval/qdrant_engine.py`
- `retrieval/context_builder.py`
- `rag/service.py`
- `rag/chunking.py`
- `rag/retriever.py`
- `storage/qdrant.py`
- `storage/obsidian.py`
- `storage/keyword_index.py`
- `backend/rag/chunker.py`
- `backend/rag/embedder.py`
- `backend/rag/indexer.py`
- `backend/rag/qdrant_store.py`
- `backend/rag/retriever.py`
- `backend/rag/obsidian_memory.py`
- `backend/context/engine.py`
- `backend/context/indexer.py`
- `backend/context/retriever.py`
- `backend/context/compressor.py`
- `anubis/memory/*`
- `anubis/context/*`

Why they overlap:

All of these implement chunks, embeddings, retrieval, context building, Qdrant storage, memory routing, vault indexing, and compression. Static analysis found duplicate `retrieve`, `search`, `upsert`, `ensure_collection`, `index_repository`, `chunker`, `retriever`, `ContextRetriever`, `ContextCompressor`, and `QdrantStore` implementations.

Best implementation:

- Best current Qdrant implementation for backend RAG: `backend/rag/qdrant_store.py`, because it uses `qdrant_client`, typed models, local fallback points, and embeds at the store boundary.
- Best broader service graph: `retrieval/*` appears more mature for optimized retrieval/routing, but it depends on root `storage` and `memory`.
- Best package destination: `anubis/memory` and `anubis/context`, after merging real implementations into them.

Recommend deleting:

- Delete root `rag/` after callers migrate.
- Delete either `backend/context/*` or `anubis/context/*` after the canonical context pipeline is chosen.
- Delete root `memory/vector.py` and `tools/vector_memory.py` after vector retrieval is unified.
- Delete one of `storage/qdrant.py`, `backend/rag/qdrant_store.py`, and `anubis/memory/qdrant_store.py`; do not keep three Qdrant clients.

Recommend merging:

- Merge into one retrieval pipeline: `VaultIndexer -> Chunker -> Embedder -> VectorStore -> Retriever -> ContextBuilder`.
- Keep separate ports for Qdrant, keyword index, Obsidian vault, and cache.
- Consolidate duplicate tokenization, keyword extraction, scoring, and Jaccard helpers.

## 7. Duplicated Qdrant Stores

Files involved:

- `storage/qdrant.py`
- `backend/rag/qdrant_store.py`
- `anubis/memory/qdrant_store.py`
- `rag-system/src/qdrant.js`

Why they overlap:

They all manage Qdrant collections and search/upsert points. `storage/qdrant.py` uses raw HTTP requests, `backend/rag/qdrant_store.py` uses `qdrant_client`, `anubis/memory/qdrant_store.py` is another memory-specific store, and `rag-system/src/qdrant.js` repeats the same idea in JavaScript.

Best implementation:

- Keep `backend/rag/qdrant_store.py` as the implementation source because it uses the official Python client and has fallback search.

Recommend deleting:

- Delete `storage/qdrant.py` after root retrieval migrates.
- Delete `anubis/memory/qdrant_store.py` after replacing it with the canonical adapter.
- Delete or archive `rag-system/src/qdrant.js` if the JS RAG service is not a separate supported product.

Recommend merging:

- Move the best Python client code into `anubis/infrastructure/qdrant`.
- Define one `VectorStore` port and make all retrieval services use it.

## 8. Duplicated API Wrappers And Servers

Files involved:

- `app/main.py`
- `api/openai_server.py`
- `api/routes/*.py`
- `backend/main.py`
- `backend/api/routes/agent.py`
- `backend/api/routes/desktop.py`
- `backend/api/routes/local.py`
- `backend/api/routes/notes.py`
- `backend/api/routes/production.py`
- `backend/api/routes/rag.py`
- `backend/api/routes/terminal.py`
- `backend/api/routes/vault_workspace.py`
- `rag-system/src/agent-service.js`

Why they overlap:

There are multiple server stacks exposing overlapping health, ask/chat, RAG, vault, terminal, and background job operations. `app/main.py` and `api/openai_server.py` both implement OpenAI-compatible streaming behavior over `runtime.agent_runner`. `backend/main.py` mounts another FastAPI app for desktop/local/product routes. `rag-system/src/agent-service.js` exposes `/health`, `/sync`, `/search`, and `/ask`.

Best implementation:

- Best FastAPI composition: `backend/main.py`, because it is modular and route-based.
- Best OpenAI-compatible details to merge: `app/main.py`, because it has richer model/chat/streaming endpoints.

Recommend deleting:

- Delete `api/openai_server.py` after FastAPI exposes the same OpenAI-compatible behavior.
- Delete root `api/routes/*` after route parity exists in the canonical API.
- Delete `rag-system/src/agent-service.js` unless the JS service is explicitly supported as an external plugin.

Recommend merging:

- Merge OpenAI-compatible endpoints from `app/main.py` into the canonical FastAPI router.
- Merge duplicate route-local helpers such as `get_indexer`, `get_retriever`, `get_agent`, and `reset_route_state` into a dependency module.

## 9. Duplicated Route Helpers And Request Models

Files involved:

- `backend/api/routes/production.py`
- `backend/api/routes/notes.py`
- `backend/api/routes/rag.py`
- `backend/api/routes/local.py`
- `backend/api/routes/desktop.py`
- `backend/api/routes/agent.py`
- `backend/api/routes/skills.py`
- `backend/api/routes/terminal.py`
- `backend/api/routes/vault_workspace.py`

Why they overlap:

Identical function bodies were found for `get_indexer` in five route files and `get_retriever` in four route files. `SearchRequest` is defined in three route files. `reset_route_state` appears in ten route files.

Best implementation:

- Put route dependencies in one module, e.g. `backend/api/dependencies.py` or future `anubis/interfaces/api/dependencies.py`.

Recommend deleting:

- Delete route-local `get_indexer`, `get_retriever`, `get_agent`, `get_vault`, and `reset_route_state` copies after centralizing.

Recommend merging:

- Merge repeated request models into shared API schemas.
- Use FastAPI dependency injection instead of ad hoc module-level factories.

## 10. Duplicated Configuration Systems

Files involved:

- `config.py`
- `backend/core/config.py`
- `anubis/core/config.py`
- `rag-system/src/config.js`
- `package.json`
- `anubis/package.json`
- `vite.config.ts`
- `anubis/vite.config.ts`
- `src-tauri/tauri.conf.json`
- `anubis/src-tauri/tauri.conf.json`

Why they overlap:

Python runtime settings are split between a large env-var module and a Pydantic `Settings` object with different defaults. `anubis/core/config.py` is empty. JS/Tauri settings are duplicated between root and nested app directories. Multiple package manifests define parallel frontend runtimes.

Best implementation:

- Keep `backend/core/config.py` style: typed `BaseSettings`, aliases, cached `settings`.
- Expand it to cover the fields currently only in root `config.py`.

Recommend deleting:

- Delete root `config.py` after all callers migrate to typed settings.
- Delete empty `anubis/core/config.py` or replace it with the canonical settings module.
- Delete `anubis/vite.config.ts` and `anubis/src-tauri/tauri.conf.json` if root Tauri is canonical.

Recommend merging:

- Merge all Python settings into one `anubis/core/config.py` using Pydantic.
- Merge frontend build settings into one chosen app.

## 11. Duplicated UI Components

Files involved:

- `src/app/ui/InputBar.tsx`
- `desktop-ui/components/InputBar.tsx`
- `src/app/ui/CommandPalette.tsx`
- `desktop-ui/components/CommandPalette.tsx`
- `src/app/App.tsx`
- `anubis/src/App.tsx`
- `src/main.tsx`
- `anubis/src/main.tsx`
- `src/app/ui/Chat.tsx`
- `src/app/ui/ChatView.tsx`
- `src/app/ui/ChatViewContainer.tsx`
- `desktop-ui/components/ChatWindow.tsx`
- `desktop-ui/components/MessageBubble.tsx`

Why they overlap:

Root Vite/Tauri and Next both implement chat input, command palette, chat surfaces, project/notes UI, and shell layout. The nested `anubis/src` app is another Vite scaffold. `InputBar` and `CommandPalette` are direct name duplicates with similar responsibilities but incompatible props and styling systems.

Best implementation:

- Best production-oriented app: root `src/` if Tauri is the intended desktop product.
- Best visual exploration: `desktop-ui/`.
- `anubis/src/` appears to be scaffold/demo code, not canonical.

Recommend deleting:

- Delete `anubis/src/` and `anubis/src-tauri/` if root Tauri remains.
- Delete `desktop-ui/` or move it to `prototypes/` if it is only a design prototype.

Recommend merging:

- Merge useful design ideas from `desktop-ui/components/*` into root `src/app/ui/*`.
- Keep one component library and one state model.

## 12. Duplicated Frontend State Management

Files involved:

- `src/app/state/anubisStore.ts`
- `src/app/core/memory.ts`
- `src/app/core/agent.ts`
- `desktop-ui/lib/data.ts`
- `desktop-ui/lib/types.ts`

Why they overlap:

Root UI has runtime state via Zustand and an in-browser/Tauri `AnubisMemory` class. `desktop-ui` has static project/chat/note state fixtures and its own type model. `src/app/core/agent.ts` also contains a compatibility `AgentMemory` shim, duplicating the memory concept.

Best implementation:

- Keep `src/app/state/anubisStore.ts` as the real UI state container if root Tauri is canonical.
- Keep `src/app/core/memory.ts` only if frontend memory is truly required; otherwise move memory to backend/application services.

Recommend deleting:

- Delete `desktop-ui/lib/data.ts` when the prototype is removed or replace it with fixtures under tests/storybook.
- Delete `AgentMemory` shim in `src/app/core/agent.ts` after callers use `AnubisMemory` or backend memory.

Recommend merging:

- Merge shared types into one frontend domain model.
- Make UI state call the same API client rather than direct local agent/memory code and backend HTTP/Tauri commands competing.

## 13. Duplicated LLM And Agent API Wrappers

Files involved:

- `llm/ollama.py`
- `anubis/llm/ollama.py`
- `backend/agent/llm.py`
- `src/app/core/agent.ts`
- `src/app/core/api.ts`
- `rag-system/src/agent-service.js`

Why they overlap:

The project has Python Ollama wrappers, a frontend direct-Ollama streaming agent, a frontend API/Tauri wrapper, and a JS RAG service that can call OpenAI. This splits model access across layers.

Best implementation:

- Keep model access backend-side as a port/adapter. `backend/agent/llm.py` is the best current backend-specific adapter.
- Keep `src/app/core/api.ts` as a thin frontend client, not `src/app/core/agent.ts` as a direct LLM runtime.

Recommend deleting:

- Delete one of `llm/ollama.py` and `anubis/llm/ollama.py`; prefer moving the surviving adapter into `anubis/infrastructure/llm/ollama.py`.
- Delete direct browser/Tauri Ollama runtime in `src/app/core/agent.ts` if the backend is canonical.

Recommend merging:

- Merge streaming response normalization into one backend API.
- Merge frontend response normalization into one generated/typed API client.

## 14. Duplicated Plugin And Skill Systems

Files involved:

- `backend/skills/plugin_manager.py`
- `runtime/plugins.py`
- `backend/skills/engine.py`
- `backend/skills/compiler.py`
- `backend/skills/self_improving_pipeline.py`
- `backend/skills/self_improving_plugins.py`
- `anubis/dsl/plugins.py`
- `anubis/dsl/skills.py`
- `anubis/dsl/compiler.py`
- `plugins/vault-memory/*`
- `.agents/skills/*`
- `skills/cybersec/*`

Why they overlap:

Skills and plugins are represented as Markdown skills, plugin manifests, DSL plugins, runtime plugins, self-improving plugins, and vault-memory plugins. `PluginManager` exists in both `backend/skills/plugin_manager.py` and `runtime/plugins.py`.

Best implementation:

- Keep `backend/skills/plugin_manager.py` as the most feature-complete plugin manager.
- Keep `backend/skills/compiler.py` if DSL validation is required.

Recommend deleting:

- Delete `runtime/plugins.py` after callers migrate.
- Delete or archive `backend/skills/self_improving_plugins.py` if it duplicates `self_improving_pipeline.py`.

Recommend merging:

- Merge plugin manifests and skill definitions under one lifecycle: discover, validate, enable, run, audit.
- Move DSL compiler/runtime into `anubis/dsl` if DSL remains productized.

## 15. Duplicated Security Analysis Logic

Files involved:

- `backend/security/security_pipeline.py`
- `backend/security/memory_security.py`
- `backend/security/attack_simulation.py`
- `backend/security/analyst_agent.py`
- `anubis/distributed/anomaly_engine.py`
- `anubis/distributed/attack_generator.py`
- `anubis/distributed/attack_executor.py`
- `anubis/distributed/defense_analyzer.py`
- `anubis/distributed/exploit_finder.py`
- `anubis/distributed/threat_intel_db.py`
- `anubis/distributed/soc_*`

Why they overlap:

Security threat detection, attack simulation, safe context building, trust scoring, tool guards, anomaly analysis, SOC ingestion, and defense analysis exist in both `backend/security` and `anubis/distributed`.

Best implementation:

- Keep `backend/security/security_pipeline.py` and `backend/security/memory_security.py` for request/context safety.
- Keep `anubis/distributed/*` only for SOC/distributed product features.

Recommend deleting:

- Delete duplicate attack simulation classes in either `backend/security/attack_simulation.py` or `anubis/distributed/attack_generator.py` after product scope is clarified.

Recommend merging:

- Merge `SafeContextBuilder`, `ToolGuard`, `TrustScorer`, and `SanitizedInput` into one security policy module used by both RAG and tool execution.

## 16. Duplicated State, Events, And Orchestration

Files involved:

- `memory/state.py`
- `anubis/core/state.py`
- `anubis/core/states.py`
- `anubis/orchestration/state.py`
- `anubis/distributed/state.py`
- `anubis/distributed/state_machine.py`
- `anubis/orchestration/state_machine.py`
- `anubis/distributed/event_bus.py`
- `anubis/orchestration/event_bus.py`
- `anubis/ui/event_stream.py`
- `runtime/orchestration_engine.py`

Why they overlap:

State transitions, event buses, orchestration events, runtime execution, and UI event streams all define similar event/state concepts independently. `EventBus`, `StateMachine`, and `OrchestrationEvent` are duplicated.

Best implementation:

- Keep `anubis/orchestration/*` for local orchestration if it is product code.
- Keep `anubis/distributed/*` only for distributed execution.

Recommend deleting:

- Delete root `memory/state.py` after runtime state migrates.
- Delete either `anubis/orchestration/state_machine.py` or `anubis/distributed/state_machine.py` if distributed/local distinction is not real.

Recommend merging:

- Create one event model and allow UI streaming to adapt it rather than defining a separate bus.

## 17. Duplicated CLI Systems

Files involved:

- `cli/*`
- `cli_mvp/*`
- `anubis/cli/*`
- `anubis_cli.py`
- `anubis_cli_mvp/__init__.py`

Why they overlap:

There are at least three CLI generations: root CLI, MVP CLI, and packaged `anubis.cli`. They duplicate command routing, rendering, sessions, themes, swarms, agents, and app entrypoints.

Best implementation:

- Keep `anubis/cli/main.py` and `anubis/cli/*` because `pyproject.toml` exposes `anubis = "anubis.cli.main:main"`.

Recommend deleting:

- Delete `cli_mvp/` and `anubis_cli_mvp/` after any tests are migrated.
- Delete root `cli/` after command behavior is ported.
- Delete `anubis_cli.py` or convert it into a thin compatibility shim.

Recommend merging:

- Merge useful terminal/session formatting from root `cli/` into `anubis/cli`.
- Merge tests to target the canonical CLI command surface.

## 18. Duplicated Small Helpers

Files involved:

- `_now_iso`: `agent/communication.py`, `agent/loop.py`, `anubis/distributed/execution_logger.py`, `anubis/distributed/terminal_service.py`, `memory/vector.py`, `memory/hermes.py`, `memory/query_cache.py`
- `jaccard`: `backend/agent/meta_agent.py`, `backend/skills/self_improving_pipeline.py`, `backend/skills/obsidian_extractor.py`, `backend/security/memory_security.py`
- `_stringify`: `anubis/distributed/validation_engine.py`, `anubis/distributed/self_reviewer.py`, `anubis/distributed/pr_generator.py`, `anubis/distributed/sandbox_runtime.py`
- `progress_callback` / `worker`: `app/main.py`, `api/openai_server.py`
- `_paths_from_text`: `backend/agent/planner.py`, `anubis/core/planner/planner.py`

Why they overlap:

Small utilities were copied into local modules instead of being centralized. This is lower risk than duplicated services, but it increases drift and inconsistent behavior.

Best implementation:

- Centralize only utilities that encode policy or repeated behavior. Avoid a giant dumping-ground `utils.py`.

Recommend deleting:

- Delete copied helper bodies after moving them to focused modules such as `time_utils`, `text_similarity`, `path_parsing`, or API streaming helpers.

Recommend merging:

- Merge `jaccard`, tokenization, compact/stringify, timestamp, and path extraction into focused utility modules under the canonical package.

## Priority Deletion List

Do not delete immediately. Delete only after import/call-site migration and tests.

1. `cli_mvp/`
2. `anubis_cli_mvp/`
3. `anubis/src/`
4. `anubis/src-tauri/`
5. `api/openai_server.py`
6. root `api/routes/`
7. root `rag/`
8. root `agent/`
9. root `tools/`
10. duplicate Qdrant store files after canonical adapter exists
11. `desktop-ui/` if it is only a prototype
12. `rag-system/` if it is not a separate supported plugin/service

## Priority Merge List

1. Merge `backend/tools/sandbox.py` into canonical `anubis` tool infrastructure.
2. Merge `backend/agent/core_loop.py` and `backend/agent/multi_agent.py` behavior into `anubis/core/agent_loop`.
3. Merge `backend/agent/verifier.py` validation into `anubis/core/verifier`.
4. Merge `backend/rag/qdrant_store.py` into a single vector-store adapter.
5. Merge route dependencies from `backend/api/routes/*` into one API dependency module.
6. Merge Python settings into one typed Pydantic settings module.
7. Merge root Tauri UI and `desktop-ui` design ideas into one chosen frontend.

## Final Recommendation

Stop adding new work to duplicate layers immediately. The safest strategy is not "clean everything at once"; it is to pick canonical homes, route new work there, then migrate and delete one duplicate family at a time. The first family to consolidate should be tools/sandboxing because duplicated security policy is the highest-risk form of duplication in this codebase.
