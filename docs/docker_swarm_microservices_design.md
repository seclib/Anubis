# ANUBIS Docker Swarm Microservice Architecture Design

Date: 2026-06-05

Role: Principal Infrastructure Engineer

## Goal

Refactor the current ANUBIS monolithic Docker setup into a microservice architecture compatible with Docker Swarm.

Required services:

- `anubis-ui`
- `anubis-core`
- `anubis-memory`
- `anubis-rag`
- `anubis-git`
- `anubis-sandbox`

This is a design-only document. No code or Docker files are modified.

## Current Docker State

ANUBIS currently ships as one hardened Python container:

```text
Dockerfile
  -> python:3.13.5-slim-bookworm pinned by digest
  -> copies bootstrap.py, src/, core/, agents/, config/
  -> read-only /app
  -> non-root UID/GID 10001
  -> ENTRYPOINT python3 /app/bootstrap.py

docker-compose.yml
  -> service: anubis
  -> image: anubis:local
  -> network_mode: none
  -> read_only: true
  -> cap_drop: ALL
  -> no-new-privileges
  -> tmpfs /tmp
  -> resource limits

optional profile:
  -> anubis-network-enabled
  -> network allowed at container layer
  -> still requires app-level network permission
```

Current runtime profile:

```text
single process
single image
in-memory state
no HTTP service
no UI service
no Qdrant service
no Git API service
no external execution worker
```

## Repository Subsystem Analysis

### Core Runtime Logic

Canonical current path:

- `bootstrap.py`
- `core/bootstrap/bootstrap.py`
- `core/graph/orchestrator.py`
- `core/graph/runner.py`
- `core/graph/nodes.py`
- `core/planner/*`
- `core/agents/*`
- `core/security/*`
- `core/observability/*`

Current graph:

```text
input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output
```

Responsibility:

- accept user stimulus
- normalize intent
- build deterministic task graph
- dispatch planner/analyst/executor/critic style agents
- call sandbox validation
- write memory records
- produce structured output
- emit traces/logs

Microservice target:

```text
anubis-core
```

### Memory System

Current modules:

- `core/memory/memory_manager.py`
- `core/memory/episodic.py`
- `core/memory/semantic.py`
- `core/memory/vector_store.py`
- `core/memory/retriever.py`
- `src/anubis/memory.py`
- `src/anubis/core_life/memory_life/*`

Current behavior:

- append-only in-memory episodic memory
- append-only in-memory semantic memory
- in-memory vector index
- scoped memory and access controls in `src/anubis/memory.py`
- no durable persistence
- no external vector database
- no Qdrant integration yet

Microservice target:

```text
anubis-memory
```

Recommended backend:

```text
Qdrant for vectors
local durable metadata store or memory wrapper API for record metadata
```

### RAG System

Current modules:

- `core/memory/retriever.py`
- `core/memory/semantic_vector_store.py`
- `core/memory/vector_store.py`
- `src/anubis/retrieval.py`
- `rag_optimization_plan.md`
- `context_builder_design.md`

Current behavior:

- deterministic hashing embeddings
- local vector search
- scoped/global routing in `src/anubis/retrieval.py`
- no external embedding service
- no external vector DB
- retrieval currently runs inside core process

Microservice target:

```text
anubis-rag
```

Responsibilities:

- query routing
- context building
- hierarchical retrieval
- chunk deduplication
- embedding cache
- compression/token budgeting
- retrieval policy enforcement

### Git Engine

Current state:

- no implemented Git service
- Git design exists in `git_experience_design.md`
- repository has Git-related audits and workflow requirements
- current Git usage is only through local CLI commands during audits

Microservice target:

```text
anubis-git
```

Responsibilities:

- branch operations
- status/diff
- staged state
- commit draft generation inputs
- PR workflow integration
- ownership detection between user and ANUBIS changes

This is a new service boundary, not an extraction from active runtime code.

### Execution Engine

Current modules:

- `core/execution/sandbox_runner.py`
- `core/security/sandbox_guard.py`
- `core/security/permission_engine.py`
- `src/anubis/execution.py`
- `src/anubis/sandbox.py`
- `terminal_design.md`
- `security_architecture.md`

Current behavior:

- active graph path validates execution requests
- `SandboxRunner` performs no direct OS execution
- `src/anubis/execution.py` has async retry/timeout/rollback concepts
- no production isolated command runner yet

Microservice target:

```text
anubis-sandbox
```

Responsibilities:

- policy-mediated execution
- sandbox profile enforcement
- isolated command runner
- terminal streaming
- resource limits
- filesystem/network isolation
- execution logs

### UI Layer

Current state:

- no web frontend
- no Tauri app
- no `package.json`
- no HTTP server
- UI designs exist in:
  - `workspace_design.md`
  - `terminal_design.md`
  - `git_experience_design.md`
  - `observability_plan.md`
  - `soc_design.md`

Microservice target:

```text
anubis-ui
```

Responsibilities:

- workspace shell
- repository/vault/git panels
- conversation view
- terminal view
- execution panel
- memory references
- SOC/security surfaces

This is a new service boundary, not an extraction from existing UI code.

## Service Decomposition Plan

### 1. anubis-ui

Type:

```text
frontend service
```

Swarm role:

```text
public ingress service
```

Responsibilities:

- serve workspace UI
- manage user session state
- show conversation
- show Git panel
- show terminal streams
- show execution status
- show memory/RAG references
- show SOC/security alerts

Primary dependencies:

- `anubis-core`
- `anubis-git`
- `anubis-sandbox` for terminal streams

Suggested protocol:

- HTTPS or internal HTTP through reverse proxy
- WebSocket/SSE for streaming execution output

State:

- stateless runtime
- browser/session state only
- no direct database ownership

Swarm placement:

- scalable replicas
- attached to public ingress and internal overlay network

Security:

- no direct access to Qdrant
- no direct access to sandbox runner internals
- no direct Docker socket
- no raw secret display

### 2. anubis-core

Type:

```text
control-plane API service
```

Swarm role:

```text
internal orchestration service
```

Responsibilities:

- expose task/session API
- run planner/executor/reviewer orchestration
- own graph state machine
- coordinate service calls
- enforce top-level policy decisions
- emit telemetry and audit events
- persist task state through memory service

Extract from:

- `core/bootstrap`
- `core/graph`
- `core/planner`
- `core/agents`
- `core/security`
- `core/observability`

Primary dependencies:

- `anubis-memory`
- `anubis-rag`
- `anubis-git`
- `anubis-sandbox`

Suggested API:

```text
POST /tasks
GET  /tasks/{id}
GET  /tasks/{id}/events
POST /tasks/{id}/approve
POST /tasks/{id}/cancel
GET  /health/live
GET  /health/ready
```

State:

- task state should be durable
- no in-memory-only production state
- stores task events through `anubis-memory` or dedicated task store

Swarm placement:

- replicated service
- replicas require idempotent task handling or task ownership lease
- start with one replica until durable coordinator/queue exists

Security:

- central authorization boundary
- does not execute OS commands directly
- does not talk to external networks except approved service calls

### 3. anubis-memory

Type:

```text
memory and vector persistence service
```

Swarm role:

```text
stateful internal service
```

Responsibilities:

- store episodic memory
- store semantic memory
- store conversation memory
- store repository memory metadata
- store vault references only
- enforce memory access policy
- expose vector collection API
- coordinate Qdrant collections
- prevent duplicate indexing

Extract from:

- `core/memory/*`
- `src/anubis/memory.py`
- `src/anubis/core_life/memory_life/*`

Recommended Qdrant collections:

```text
anubis_repository_memory
anubis_conversation_memory
anubis_vault_memory
anubis_execution_memory
```

Suggested API:

```text
POST /memory/records
GET  /memory/records/{id}
POST /memory/query
POST /memory/vector/upsert
POST /memory/vector/search
GET  /memory/snapshot
GET  /health/ready
```

State:

- persistent volume for Qdrant
- persistent volume for metadata store if wrapper owns metadata

Swarm placement:

- pinned to manager or labeled storage node
- one replica for Qdrant unless clustered Qdrant is intentionally introduced
- persistent named volume

Security:

- internal overlay network only
- no public ingress
- enforce access scopes and sensitivity
- deny raw secret storage
- vault entries are references only

### 4. anubis-rag

Type:

```text
retrieval and context service
```

Swarm role:

```text
internal stateless service with cache
```

Responsibilities:

- route retrieval queries
- build task context
- rank files and memory records
- apply token budgets
- compress context
- deduplicate chunks
- manage embedding cache
- query `anubis-memory`
- return 3-5 task-relevant files where possible

Extract from:

- `core/memory/retriever.py`
- `core/memory/semantic_vector_store.py`
- `src/anubis/retrieval.py`
- future context builder from `context_builder_design.md`
- future RAG optimization from `rag_optimization_plan.md`

Suggested API:

```text
POST /rag/query
POST /rag/context
POST /rag/index/repository
POST /rag/index/conversation
POST /rag/chunks/deduplicate
GET  /rag/cache/stats
GET  /health/ready
```

State:

- mostly stateless
- optional local LRU/cache
- persistent embedding cache can live in `anubis-memory`

Swarm placement:

- horizontally scalable
- internal overlay network only
- cache can be per-replica initially

Security:

- no raw secret indexing
- obey memory access controls
- no direct vault value retrieval
- no public ingress

### 5. anubis-git

Type:

```text
Git workspace service
```

Swarm role:

```text
internal service with mounted repository/worktree volume
```

Responsibilities:

- repository status
- branch creation
- worktree management
- diff generation
- staged state
- commit workflow
- PR workflow
- ownership detection
- CI/PR status polling when explicitly network-enabled

Based on:

- `git_experience_design.md`

Suggested API:

```text
GET  /git/status
POST /git/branches
GET  /git/diff
POST /git/stage
POST /git/commit/draft
POST /git/commit
POST /git/pr/draft
POST /git/pr/create
GET  /git/pr/status
GET  /health/ready
```

State:

- repository/worktree volume
- task branch metadata
- no direct memory ownership

Swarm placement:

- one replica per workspace/repository
- pinned to node with repository volume
- internal overlay network

Security:

- no direct write without core approval
- network disabled by default
- PR creation requires explicit network permission
- force push disabled by default

### 6. anubis-sandbox

Type:

```text
execution worker service
```

Swarm role:

```text
isolated internal worker
```

Responsibilities:

- execute approved commands
- validate sandbox requests
- enforce filesystem/network/resource policy
- stream output
- maintain execution logs
- run tests/builds
- support fixture/worktree execution
- return structured evidence

Extract from:

- `core/execution/sandbox_runner.py`
- `src/anubis/execution.py`
- `src/anubis/sandbox.py`
- `core/security/sandbox_guard.py`
- `terminal_design.md`
- `security_architecture.md`

Suggested API:

```text
POST /sandbox/validate
POST /sandbox/commands
GET  /sandbox/commands/{id}
GET  /sandbox/commands/{id}/stream
POST /sandbox/commands/{id}/cancel
GET  /sandbox/profiles
GET  /health/ready
```

State:

- ephemeral execution state
- durable execution logs should be persisted through `anubis-memory` or observability store
- scratch/worktree mounts as needed

Swarm placement:

- constrained worker nodes
- no public ingress
- strict resource limits
- no Docker socket by default
- default network egress disabled

Security:

- most locked-down service
- read-only root filesystem
- non-root
- no-new-privileges
- drop capabilities
- tmpfs scratch
- per-command timeout/memory/PID limits
- command execution only after `anubis-core` approval

## Responsibility Map

| Responsibility | anubis-ui | anubis-core | anubis-memory | anubis-rag | anubis-git | anubis-sandbox |
| --- | --- | --- | --- | --- | --- | --- |
| Workspace shell | Owns | Uses | No | No | Uses | Uses |
| Conversation UI | Owns | API source | Stores records | Provides context | No | Streams execution |
| Task orchestration | No | Owns | Stores task memory | Supplies context | Supplies repo state | Executes approved work |
| Planning | No | Owns | No | Context input | Repo input | No |
| Agent dispatch | No | Owns | No | Context input | No | No |
| Memory records | Reads via core | Coordinates | Owns | Reads/searches | No | Writes evidence via core |
| Vector storage | No | No | Owns | Queries | No | No |
| RAG routing | No | Requests | Provides records | Owns | Provides repo files/diffs | No |
| Context builder | Displays | Requests | Provides memory | Owns | Provides file status | No |
| Git status/diff | Displays | Coordinates | No | May consume diffs | Owns | No |
| Commit/PR workflow | Displays | Approval/orchestration | Stores evidence | No | Owns | No |
| Execution policy | Displays | Owns decision | No | No | Enforces Git gates | Enforces command gates |
| Command execution | Displays stream | Approves | Stores evidence | No | Limited Git commands | Owns |
| Sandbox isolation | Displays state | Policy owner | No | No | Calls if needed | Owns runner |
| Audit/telemetry | Displays | Owns correlation | Stores or emits | Emits | Emits | Emits |
| Health checks | Displays | Owns aggregate | Own health | Own health | Own health | Own health |

## Communication Flow Diagram

### Primary Task Flow

```text
User
  -> anubis-ui
     -> POST /tasks
        -> anubis-core
           -> anubis-rag: build context
              -> anubis-memory: retrieve memory/vector candidates
              <- ranked context
           <- compressed task context
           -> anubis-git: read repo status/diff/file metadata
           <- repository state
           -> planner/executor/reviewer orchestration
           -> anubis-sandbox: validate or execute approved command
              -> stream logs/events
           <- execution result/evidence
           -> anubis-memory: append task episode, semantic facts, execution evidence
        <- task result and event stream
  <- conversation updates, diff, terminal output, memory refs
```

### RAG Query Flow

```text
anubis-core
  -> anubis-rag
     -> classify query
     -> route repository/conversation/vault/execution retrieval
     -> anubis-memory / Qdrant wrapper
        -> vector search
        -> access filtering
     <- candidates
     -> rank, deduplicate, compress
  <- context packet
```

### Memory Write Flow

```text
anubis-core or anubis-sandbox
  -> anubis-memory
     -> validate memory policy
     -> reject raw secrets
     -> persist metadata
     -> upsert vector through Qdrant wrapper
     -> emit audit/telemetry
  <- memory record id and vector cursor
```

### Git Commit/PR Flow

```text
anubis-ui
  -> anubis-core: approve commit or PR action
     -> anubis-git: inspect staged set
     <- diff summary and risk metadata
     -> anubis-core: reviewer decision
     -> anubis-git: create commit or draft PR
        -> optional network only after approval
     <- commit hash or PR URL
     -> anubis-memory: store Git evidence
  <- updated workspace state
```

### Sandbox Execution Flow

```text
anubis-core
  -> anubis-sandbox: command request
     -> permission/sandbox policy check
     -> select sandbox profile
     -> run isolated process or validation-only request
     -> stream stdout/stderr/status
     -> emit audit/metrics/traces
  <- command result
  -> anubis-memory: persist execution evidence
```

### Health Aggregation Flow

```text
anubis-ui
  -> anubis-core: GET /health/ready
     -> anubis-memory: /health/ready
     -> anubis-rag: /health/ready
     -> anubis-git: /health/ready
     -> anubis-sandbox: /health/ready
  <- aggregate health
```

## Docker Swarm Network Design

Recommended overlay networks:

```text
anubis-public
  anubis-ui only

anubis-control
  anubis-ui
  anubis-core

anubis-data
  anubis-core
  anubis-memory
  anubis-rag

anubis-execution
  anubis-core
  anubis-sandbox
  anubis-git

anubis-observability
  all services emit telemetry
```

Network rules:

- `anubis-memory` has no public ingress.
- `anubis-rag` has no public ingress.
- `anubis-git` has no public ingress.
- `anubis-sandbox` has no public ingress.
- `anubis-ui` cannot call memory directly.
- `anubis-ui` cannot call sandbox directly for mutating commands unless core brokers approval.
- Network egress from `anubis-sandbox` is disabled by default.
- Network egress from `anubis-git` is disabled except explicit PR/Git remote workflows.

## Swarm Stack Shape

Conceptual stack:

```yaml
services:
  anubis-ui:
    networks: [anubis-public, anubis-control]
    replicas: 2

  anubis-core:
    networks: [anubis-control, anubis-data, anubis-execution, anubis-observability]
    replicas: 1 initially

  anubis-memory:
    networks: [anubis-data, anubis-observability]
    replicas: 1
    volumes: [anubis-memory-data]

  anubis-rag:
    networks: [anubis-data, anubis-observability]
    replicas: 2

  anubis-git:
    networks: [anubis-execution, anubis-observability]
    replicas: 1 per workspace
    volumes: [workspace-repo]

  anubis-sandbox:
    networks: [anubis-execution, anubis-observability]
    replicas: 1..N
    read_only: true
    cap_drop: [ALL]
```

This is not a final Compose file. It is the target Swarm service model.

## Image Strategy

Current image:

```text
anubis:local
```

Target images:

```text
anubis-ui:<version>
anubis-core:<version>
anubis-memory:<version>
anubis-rag:<version>
anubis-git:<version>
anubis-sandbox:<version>
```

Recommended migration:

1. Keep one base Python runtime image for shared Python services.
2. Build service-specific images with only required modules.
3. Keep `anubis-ui` independent from Python runtime if a frontend stack is introduced.
4. Use official Qdrant image if `anubis-memory` delegates vector persistence to Qdrant.
5. Keep sandbox image minimal and hardened separately.

## Data and Volume Model

| Volume | Owner | Purpose |
| --- | --- | --- |
| `anubis-memory-data` | `anubis-memory` | Qdrant/vector and memory metadata persistence |
| `anubis-observability-data` | core or telemetry sidecar | logs, traces, metrics, audit if local-first |
| `workspace-repo` | `anubis-git` and controlled sandbox mounts | repository/worktree access |
| `anubis-sandbox-scratch` | `anubis-sandbox` | ephemeral task execution scratch |

Rules:

- `anubis-core` should not mount the repository directly unless needed for bootstrap compatibility.
- `anubis-ui` should mount no repository or secret volumes.
- `anubis-sandbox` should mount worktrees read-only by default and scratch writable.
- `anubis-memory` owns durable memory data.

## Security Model for Swarm

Carry forward current Docker hardening:

- non-root UID/GID
- read-only root filesystem
- `no-new-privileges`
- drop all capabilities
- tmpfs for scratch paths
- memory/PID/CPU limits
- no default external network

Additional Swarm requirements:

- use Docker secrets/configs instead of inline env secrets
- isolate overlay networks by function
- constrain stateful services to labeled nodes
- do not mount Docker socket into `anubis-sandbox`
- require explicit service-to-service identity or shared secret/mTLS later
- keep `anubis-memory` and `anubis-sandbox` private

## Migration Plan

### Phase 1: API Contract Extraction

Define stable APIs for:

- task orchestration
- memory write/query
- RAG context/query
- Git status/diff/commit/PR
- sandbox validate/execute
- health checks

No service split yet.

### Phase 2: Core API Service

Convert CLI graph runtime into `anubis-core` API facade while preserving CLI entrypoint.

Keep memory/RAG/sandbox in-process behind adapters.

### Phase 3: Memory Service

Extract `MemoryManager` and `SharedMemory` into `anubis-memory`.

Introduce:

- durable metadata
- Qdrant wrapper or Qdrant sidecar/backend
- collection naming
- access-control enforcement

### Phase 4: RAG Service

Extract retrieval/context building into `anubis-rag`.

Core calls RAG instead of directly constructing retrieval responses.

### Phase 5: Sandbox Service

Extract validation/execution into `anubis-sandbox`.

Start with validation-only parity, then add isolated runner.

### Phase 6: Git Service

Introduce `anubis-git` from the design contract.

Mount repository/worktree volume only into Git service and sandbox fixtures.

### Phase 7: UI Service

Introduce `anubis-ui`.

UI talks to core, not directly to memory/sandbox for mutating operations.

### Phase 8: Swarm Stack

Replace current Compose-only local profile with:

- development Compose stack
- production Swarm stack
- service-specific images
- overlay networks
- placement constraints
- rolling update policies
- health checks

## Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Current runtime is not HTTP/API based | High | Add API facade before splitting services. |
| Memory is in-memory only | High | Extract memory before scaling core replicas. |
| Qdrant is not currently integrated | Medium-High | Introduce memory wrapper first, then Qdrant backend. |
| Sandbox is validation-only today | High | Preserve validation parity before adding real execution. |
| No UI exists | Medium | Treat `anubis-ui` as new service driven by workspace design. |
| Git service does not exist | Medium | Build from explicit Git design contract. |
| Swarm stateful volume placement | Medium | Pin stateful services to labeled nodes. |
| Service-to-service security | Medium | Start with private overlay networks, add mTLS/auth later. |

## Target Architecture Summary

```text
anubis-ui
  user workspace, conversation, terminal, git/memory/security panels

anubis-core
  orchestration, planning, agent dispatch, approvals, policy coordination

anubis-memory
  durable memory records, Qdrant/vector collections, access control

anubis-rag
  retrieval routing, context builder, chunk dedupe, token budgeting

anubis-git
  repository state, branches, diffs, commits, PR workflows

anubis-sandbox
  sandbox validation, isolated execution, streaming logs, resource limits
```

## Final Communication Diagram

```text
                         ┌────────────────┐
                         │   anubis-ui    │
                         │ workspace UX   │
                         └───────┬────────┘
                                 │
                         public/control API
                                 │
                         ┌───────▼────────┐
                         │  anubis-core   │
                         │ orchestration  │
                         └─┬─────┬─────┬──┘
                           │     │     │
              context/RAG  │     │     │ sandbox/exec
                           │     │     │
                  ┌────────▼─┐   │   ┌─▼────────────┐
                  │anubis-rag│   │   │anubis-sandbox│
                  │retrieval │   │   │execution     │
                  └────┬─────┘   │   └──────┬───────┘
                       │         │          │
                       │ memory  │ git      │ execution evidence
                       │ query   │ ops      │
                  ┌────▼─────────▼──┐       │
                  │  anubis-memory  │◄──────┘
                  │ memory/Qdrant   │
                  └─────────────────┘
                           ▲
                           │
                    ┌──────┴──────┐
                    │ anubis-git  │
                    │ repo engine │
                    └─────────────┘
```

This design converts ANUBIS from a single local-first hardened container into a Swarm-compatible control plane with isolated data, retrieval, Git, and execution services while preserving the existing security posture as the baseline.
