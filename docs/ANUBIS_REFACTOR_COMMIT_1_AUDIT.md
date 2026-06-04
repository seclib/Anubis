# ANUBIS Refactor Commit 1: Full Audit & Mapping

## Commit Goal

Understand the current ANUBIS system as it actually runs before further refactoring.

This commit intentionally does not change runtime behavior. It maps components,
execution paths, duplicated responsibilities, and current architectural risks.

## Current Components

### Active UI Surfaces

- `src/app/core/api.ts`
  - Browser/Tauri chat client.
  - Browser path sends user messages to `POST /ask`.
  - Tauri path invokes `agent_chat`.
  - Health check calls `/health/live`.
- `src/app/core/terminal.ts`
  - Browser terminal client for `/api/terminal/*`.
- `src/app/core/vaultWorkspace.ts`
  - Browser vault client for `/api/vault/*`.
- `anubis/cli/main.py`
  - Python CLI entrypoint.
- `anubis/cli/loop.py`
  - CLI command loop and natural-language routing.

### Active Backend API Surface

- `backend/main.py`
  - FastAPI app.
  - Registers health, production, desktop, local, notes, RAG, agent, skills,
    git, terminal, vault, and brain routers.
- `backend/api/routes/production.py`
  - `/ask`, `/sync`, `/memory`.
- `backend/api/routes/agent.py`
  - `/agent/chat`.
- `backend/api/routes/desktop.py`
  - `/assistant/chat`, notes, library, search.
- `backend/api/routes/local.py`
  - local read/write/search/embed and `/agent_query`.
- `backend/api/routes/terminal.py`
  - terminal session creation, command execution, events.
- `backend/api/routes/health.py`
  - `/health`, `/health/live`, `/health/ready`.

### Agent Implementations Found

#### Current Unified Core Candidate

- `anubis/core/session.py`
  - `SessionRuntime`
  - `AgentOrchestrator`
  - `RunGuard`
  - This is the clearest current candidate for the single Agent Core.
  - It coordinates planning, memory retrieval, model routing, tool execution,
    review, streaming events, and fallback behavior.

- `anubis/agents/session.py`
  - `PlannerAgent`
  - `ExecutorAgent`
  - `ReviewerAgent`
  - Used by `anubis.core.session`.

#### HTTP Compatibility Agent

- `backend/agent/loop.py`
  - Legacy HTTP chat facade.
  - Currently delegates decision-making to `anubis.core.session.SessionRuntime`
    while preserving old HTTP response fields.

- `backend/agent/async_loop.py`
  - Async wrapper used by `/ask`.
  - Currently delegates to `backend.agent.loop.AgentLoop`.

#### Tested Legacy Execution Engine

- `backend/agent/agent_loop.py`
  - Planner/executor/verifier loop with task lifecycle logging.
  - Heavily covered by phase tests.
  - Still active as a tested internal engine, but not the main UI chat path.

- `backend/agent/planner.py`
- `backend/agent/executor.py`
- `backend/agent/verifier.py`
- `backend/agent/task_manager.py`
  - Support the tested legacy execution engine.

#### Multi-Agent / Experimental Systems

- `backend/agent/multi_agent.py`
  - Multi-agent planner/executor/critic loop.
  - Covered by tests, but overlaps with the unified core and legacy execution loop.

- `backend/agent/core_loop.py`
  - Another agent loop implementation.

- `backend/agent/meta_agent.py`
  - Meta-agent and skill-oriented orchestration.

- `anubis/core/agent_loop/*`
  - A separate production-style agent-loop abstraction.

- `anubis/agents/*`
  - Generic agent registry, manager, swarm, and role modules.

- `anubis/distributed/*`
  - Distributed/autonomous planner, executor, reviewer, orchestration,
    scheduling, worker pool, SOC/security, CI/CD, PR generation, rollback,
    terminal, sandbox, and governance systems.

- `agent/*`
  - Top-level historical monolithic agent runtime.
  - `runtime/agent_runner.py` still references `agent.loop.run_agent_loop`.

- `runtime/*`
  - Separate runtime/orchestration stack used by `app/main.py` and
    `api/openai_server.py`.

- `cli/*` and `cli_mvp/*`
  - Legacy CLI/MVP implementations.

### Memory / RAG Components Found

- `backend/rag/*`
  - Active backend RAG indexing, retrieval, embedding, Qdrant integration.
- `backend/vault/*`
  - Active markdown vault read/write layer.
- `anubis/memory/*`
  - Newer memory modules plus session memory.
- `retrieval/*`
  - Separate retrieval pipeline and memory router.
- `rag/*`
  - Top-level alternate RAG service.
- `memory/*`
  - Top-level historical memory modules.

### Tools Components Found

- `backend/tools/*`
  - Active backend tool execution and sandbox validation.
- `anubis/tools/*`
  - Session tools and tool execution engine used by `SessionRuntime`.
- `tools/*`
  - Top-level legacy tools.
- `anubis/distributed/sandbox_runtime.py`
  - Sandboxed command runtime used by terminal service.

## Current Execution Flow

### Browser Chat Flow

```text
src/app/core/api.ts
  sendAgentMessage()
    -> POST /ask
      -> backend.api.routes.production.ask()
        -> backend.agent.async_loop.AsyncAgentLoop.run()
          -> backend.agent.loop.AgentLoop.chat()
            -> anubis.core.session.SessionRuntime.run()
              -> AgentOrchestrator.run()
                -> PlannerAgent.plan()
                -> SessionMemory.retrieve()
                -> ExecutorAgent.decide()
                -> ToolExecutionEngine.execute()
                -> ReviewerAgent.review()
              -> session.done event
        -> normalized HTTP response
```

### CLI Natural-Language Flow

```text
anubis.cli.main
  -> anubis.cli.loop.run_loop() / run_commands()
    -> is_agent_turn()
      -> anubis.core.session.SessionRuntime.run()
        -> AgentOrchestrator.run()
          -> PlannerAgent / ExecutorAgent / ReviewerAgent
          -> SessionMemory + ToolExecutionEngine
        -> TerminalRenderer.render_stream()
```

### Backend Chat Alias Flow

```text
/agent/chat
/assistant/chat
/agent_query
  -> backend.agent.loop.AgentLoop.chat()
    -> anubis.core.session.SessionRuntime.run()
    -> legacy-compatible response shape
```

### Terminal Flow

```text
src/app/core/terminal.ts
  -> /api/terminal/sessions
  -> /api/terminal/sessions/{id}/commands
    -> backend.api.routes.terminal
      -> anubis.distributed.terminal_service.TerminalService
        -> PermissionManager
        -> IsolatedToolExecutor
        -> SandboxRuntime
```

### Legacy OpenAI-Compatible Flow

```text
app/main.py or api/openai_server.py
  -> runtime.agent_runner.run_agent_loop()
    -> agent.loop.run_agent_loop()
```

This is separate from the current desktop API path and should be treated as a
legacy compatibility surface until explicitly retained or retired.

## Problems Found

### 1. Too Many Agent Cores

The repository still contains several decision-making loops:

- `anubis.core.session`
- `backend.agent.agent_loop`
- `backend.agent.multi_agent`
- `backend.agent.core_loop`
- `anubis.core.agent_loop`
- `anubis.distributed`
- `agent.loop`
- `runtime.orchestration_engine`
- `cli/anubis.py`
- `cli_mvp`

This increases risk because contributors cannot easily tell which agent loop is
canonical.

### 2. Multiple HTTP Chat Paths

The user-facing chat paths are:

- `/ask`
- `/agent/chat`
- `/assistant/chat`
- `/agent_query`
- Tauri `agent_chat`

These now mostly converge, but the route surface is still duplicated.

### 3. Memory Is Not Yet Passive Enough

Several retrieval/memory modules include routing, scoring, or policy logic:

- `retrieval/memory_router.py`
- `retrieval/optimized.py`
- `anubis/memory/router.py`
- `backend/rag/retriever.py`

The final target wants memory to be passive read/write storage, with decisions
kept in Agent Core.

### 4. Tools Layers Overlap

There are at least three tool families:

- `backend/tools`
- `anubis/tools`
- top-level `tools`

Some tools execute commands directly, while others use sandbox layers. Tool
responsibilities must be narrowed to execution only.

### 5. Legacy Runtime Surfaces Remain

`app/main.py`, `api/openai_server.py`, and `runtime/*` still route to the
top-level `agent.loop` runtime. These are not aligned with the current desktop
API flow.

### 6. Distributed System Is Broad And Separate

`anubis/distributed` is large and heavily tested, but it contains its own
planner/executor/reviewer concepts. It should either become a service around
the unified Agent Core or remain explicitly out-of-band.

### 7. UI Still Has Some Local Intelligence

`src/app/core/agent.ts` includes a local browser Ollama agent pipeline. If it is
still reachable, it violates the target rule that UI must be dumb. Current
browser chat uses `src/app/core/api.ts`, but this module remains a risk.

## Current Architecture Diagram

```text
                         +----------------------+
                         |      UI Surfaces     |
                         |  src app / CLI / API |
                         +----------+-----------+
                                    |
              +---------------------+---------------------+
              |                                           |
      Current desktop path                         Legacy surfaces
              |                                           |
              v                                           v
     backend.main: FastAPI                         app/main.py, api/*
              |                                           |
      +-------+--------+                                  |
      |                |                                  |
   /ask          chat aliases                             |
      |                |                                  |
      v                v                                  v
 backend.agent.async_loop      runtime.agent_runner -> agent.loop
      |
      v
 backend.agent.loop
      |
      v
 anubis.core.session.SessionRuntime
      |
      v
 AgentOrchestrator
      |
      +--> anubis.agents.session Planner/Executor/Reviewer
      +--> anubis.memory.session
      +--> anubis.tools engine/session_tools
      +--> anubis.llm Ollama router/client
```

## Commit 1 Architecture State

The codebase is partially unified:

- Browser `/ask`, `/agent/chat`, `/assistant/chat`, `/agent_query`, and CLI
  natural-language turns route through `anubis.core.session.SessionRuntime`.
- Terminal execution routes through the distributed terminal/sandbox service.
- Legacy OpenAI-compatible surfaces still route through `runtime` and top-level
  `agent.loop`.
- Tested legacy backend agent components remain present and must be handled
  carefully in later commits.

## Risks For Commit 2

- Removing `backend.agent.agent_loop` too early would break phase tests.
- Removing `backend.agent.multi_agent` too early would break multi-agent tests.
- Removing `runtime` or top-level `agent` may break OpenAI-compatible API paths.
- `src/app/core/agent.ts` may be unused by the active UI, but should be checked
  before deletion.
- Route consolidation must preserve response shapes for existing clients.

## Recommended Commit 2 Focus

Commit 2 should centralize named Agent Core ownership without deleting the
heavily tested legacy engines yet:

1. Make `anubis.core.session` the explicit canonical Agent Core.
2. Add or rename a small public core entrypoint only if necessary.
3. Redirect remaining reachable runtime surfaces to the core where safe.
4. Deactivate UI-local agent decision code if it is unused by active screens.
5. Keep old agent engines as compatibility/test modules until Commit 3 cleanup.
