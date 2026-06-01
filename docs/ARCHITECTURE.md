# Anubis Desktop OS Architecture

This document preserves the advanced technical architecture for Anubis Desktop OS.

For production folder boundaries and desktop entrypoints, also see
[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md).

## System Overview

Anubis is organized as a local desktop system with five major layers:

```text
Desktop launcher
  -> React dashboard and workspace
  -> FastAPI desktop backend
  -> RAG, vault, memory, and graph services
  -> autonomous and multi-agent cognition runtime
```

Primary entrypoints:

- Desktop shell: `desktop/src-tauri/src/main.rs`
- React app: `desktop/src/main.tsx`
- Desktop backend: `backend.main:app`
- Launcher service manager: `desktop/src-tauri/src/service_manager.rs`
- Desktop chat adapter: `backend.agent.loop.AgentLoop`
- Autonomous runtime composition: `runtime.agent_runner.AgentRunner`

The launcher owns process lifecycle. The backend owns HTTP and WebSocket APIs.
The frontend talks to the launcher through Tauri commands and to the backend
through local HTTP/WebSocket endpoints.

## Multi-Agent System

The multi-agent roster lives in `agent/multi_agent.py`.

Current agent roles:

- `orchestrator_agent`: coordinates the system and assigns work.
- `planner_agent`: breaks goals into executable steps.
- `coder_agent`: implements code changes.
- `reviewer_agent`: reviews quality and risk.
- `tester_agent`: validates behavior with commands and tests.
- `debugger_agent`: analyzes failures and proposes recovery.
- `memory_agent`: preserves compact shared context.

Agent metadata is represented with `AgentSpec`:

```text
name
role
model
prompt
```

The multi-agent layer is intentionally lightweight. It defines roles, prompts,
message helpers, and collaboration context. It does not directly own concrete
tool execution or persistent storage.

Runtime wiring happens through dependency injection:

```text
runtime.agent_runner
  -> agent loop callable
  -> AgentDependencies
  -> tool runner
  -> memory store
  -> stateless LLM-backed agent caller
```

This keeps the agent layer testable and prevents circular imports.

## RAG Architecture

RAG means Anubis can answer using local saved knowledge instead of relying only
on the model context.

Desktop RAG modules:

```text
backend/vault/service.py      Markdown vault access
backend/vault/markdown.py     Markdown section parsing
backend/rag/chunker.py        note -> chunks
backend/rag/embedder.py       local embedding adapter
backend/rag/qdrant_store.py   Qdrant collection access
backend/rag/indexer.py        full vault indexing
backend/rag/retriever.py      search interface
backend/api/routes/rag.py     HTTP routes
```

Flow:

```text
Markdown notes
  -> split into sections
  -> convert sections to chunks
  -> embed chunk text
  -> store vectors in Qdrant
  -> retrieve relevant chunks during assistant chat
```

Important boundaries:

- Vault owns Markdown I/O.
- Chunking is deterministic and rebuildable.
- Qdrant stores searchable vector points.
- The agent does not directly manipulate Qdrant.
- RAG failures should degrade gracefully and not prevent a final assistant response.

## Skill DNA System

The Skill DNA system treats skills as evolvable definitions rather than static
helper text.

Skill files are read from the skills directory exposed by
`backend.api.routes.skills.get_skills_dir`.

Supported skill metadata includes:

- skill identity
- objective
- dependencies
- triggers
- mutation rules
- fitness values
- source Markdown

The goal is to let Anubis reason about the usefulness, relationships, and
evolution of skills over time.

Conceptual model:

```text
Skill DNA
  -> identity
  -> objective
  -> dependencies
  -> triggers
  -> mutation rules
  -> fitness
  -> evolution history
```

Current implementation surfaces this through:

- `agent/skill_ecosystem_graph.py`
- `backend/api/routes/skills.py`
- `desktop/src/SkillGraphView.tsx`
- `desktop/src/CognitiveGraphView.tsx`

## Graph Engine

Anubis has two graph-facing layers:

### Skill Ecosystem Graph

The skill graph is built from skill files and inferred relationships.

It exposes:

- nodes
- edges
- clusters
- insights
- changes
- evolution paths

API endpoints:

```text
GET /api/skills
GET /api/skill-graph
GET /api/skill-updates
```

The `skill-updates` endpoint streams graph changes to the frontend.

### Cognitive Graph View

The Cognitive Graph View uses Cytoscape.js to combine:

- skills
- agents
- memory clusters
- system nodes
- relationships
- evolution events

Frontend implementation:

```text
desktop/src/CognitiveGraphView.tsx
```

The graph is composed from live brain snapshots plus live skill graph updates:

```text
/brain/ws
  + /api/skill-updates
  -> CognitiveGraphView
```

This provides a foundation for future advanced graph visualizations without
coupling the graph UI directly to backend internals.

## Loop Cognition

The autonomous agent loop follows an observe-plan-act-reflect-finalize shape.

Recommended production loop:

```text
user request
  -> observe current context
  -> retrieve memory
  -> route intent
  -> plan if needed
  -> act through registered tools
  -> inspect result
  -> repair or continue when needed
  -> finalize response
```

Core invariant:

```text
Every run must reach a final user response, even when a tool, model call,
memory lookup, or verification step fails.
```

Safeguards expected around the loop:

- maximum step count
- retry limits
- command timeouts
- output size limits
- non-progress detection
- structured errors
- final response fallback

Runtime routing is isolated in `runtime/router.py`. It classifies parsed actions
without executing side effects:

```text
plan
tool
llm
final
invalid
```

Tool execution remains behind the executor boundary.

## Self-Modifying Runtime

The self-modifying runtime is implemented in:

```text
agent/self_modifying_runtime.py
```

Its purpose is to allow controlled behavior updates without arbitrary source
rewriting.

Core pieces:

- `DynamicFunctionRegistry`: registry of callable runtime functions.
- `RuntimePatchPolicy`: policy wrapper for approved behavior.
- `VersionStore`: stores prior versions for rollback.
- patch validation helpers: normalize and validate proposals.
- apply and rollback helpers: update behavior or restore previous behavior.

High-level flow:

```text
agent proposes runtime patch
  -> normalize patch
  -> validate target function and schema
  -> review decision
  -> apply policy wrapper
  -> record version
  -> allow rollback
```

Safety properties:

- only registered functions can be patched
- validation happens before application
- previous behavior can be restored
- decisions are logged as explicit runtime events
- arbitrary source mutation is avoided

The runtime architecture description is exposed through
`runtime_architecture()` for dashboards and control surfaces.

## Dependency Direction

The stable dependency direction is:

```text
cli / api / desktop
  -> runtime
    -> agent
    -> executor
    -> tools
    -> memory
    -> llm
      -> core / config
```

Rules:

- `tools` must not import `agent`.
- `executor` must not import `agent`.
- `memory` must not import `agent`, `executor`, or `tools`.
- `llm` must stay stateless.
- UI code must not contain agent reasoning logic.
- tool execution must pass through the executor boundary.
- final user-facing output must pass through the agent finalization path.

## Observability

Important observability surfaces:

- launcher logs emitted as `anubis-log`
- watchdog events emitted as `anubis-watchdog`
- backend logs through `anubis.api`
- RAG logs through `anubis.rag.*`
- vault logs through `anubis.vault`
- brain dashboard snapshots through `/brain/snapshot`
- live dashboard updates through `/brain/ws`

The dashboard intentionally separates:

- service health
- memory statistics
- agent activity
- live logs
- architecture and graph views

## Compatibility Notes

The repository still contains older CLI and OpenAI-compatible API paths:

- `app/`
- root `main.py`
- root `rag/`
- `retrieval/`
- `runtime/`

They remain available for compatibility. New Desktop OS work should prefer
additive adapters and tests over large moves until legacy entrypoints have
dedicated migration coverage.
