# ANUBIS Microservice Communication Design

Date: 2026-06-05

Role: Distributed Systems Engineer

## Goal

Design the communication system between ANUBIS microservices.

Required flows:

- how core talks to memory
- how core talks to RAG
- how Git engine is triggered
- how sandbox executes tasks
- how UI receives updates

Design constraints:

- low latency
- simple protocol
- no tight coupling
- failure-tolerant behavior

## Current Context

The Swarm target services are:

- `anubis-ui`
- `anubis-core`
- `anubis-memory`
- `anubis-rag`
- `anubis-git`
- `anubis-sandbox`

The current repository does not yet implement long-running HTTP API servers for each service. This document defines the service communication contract those APIs should implement.

## Protocol Strategy

Use a simple tiered approach:

```text
HTTP/JSON
  default synchronous request/response protocol

SSE
  default UI event stream and task update protocol

WebSocket
  optional bidirectional terminal stream protocol

gRPC
  optional future protocol for high-throughput sandbox streams or RAG batch retrieval

NATS
  optional event bus for async events, fanout, retries, and durable task/event workflows
```

Recommended first implementation:

```text
HTTP/JSON + SSE
```

Reason:

- easiest to debug
- compatible with Swarm service DNS
- low operational overhead
- fits current Python standard-library/minimal dependency posture
- avoids overcoupling to a broker before task/event volumes justify it

Recommended second phase:

```text
HTTP/JSON + SSE + NATS JetStream
```

Reason:

- durable event replay
- async fanout
- better failure recovery
- clean SOC/observability integration

## Communication Architecture Diagram

```text
                         browser
                           │
                 HTTP + SSE/WebSocket
                           │
                    ┌──────▼──────┐
                    │ anubis-ui   │
                    └──────┬──────┘
                           │ HTTP/SSE
                           │ anubis-control
                    ┌──────▼──────┐
                    │ anubis-core │
                    │ orchestrator│
                    └─┬────┬────┬─┘
                      │    │    │
          HTTP/JSON   │    │    │ HTTP/JSON
       anubis-data    │    │    │ anubis-execution
                      │    │    │
          ┌───────────▼┐   │   ┌▼──────────────┐
          │ anubis-rag │   │   │ anubis-git    │
          │ context    │   │   │ repo workflow │
          └─────┬──────┘   │   └───────────────┘
                │          │
                │ HTTP     │ HTTP/Qdrant API
                │          │
          ┌─────▼──────────▼┐
          │ anubis-memory   │
          │ Qdrant + memory │
          └─────────────────┘

                    ┌────────────────┐
                    │ anubis-sandbox │
                    │ isolated exec  │
                    └───────▲────────┘
                            │
            HTTP command API + SSE/WebSocket output stream
                            │
                      anubis-core

Optional async plane:

          ┌──────────────────────────────────────┐
          │ NATS / Redis Streams event bus       │
          │ task.*, memory.*, rag.*, git.*,      │
          │ sandbox.*, ui.*, audit.*, soc.*      │
          └──────────────────────────────────────┘
```

## Communication Rules

### Rule 1: Core Is the Control Plane

`anubis-core` brokers all mutating actions.

The UI should not directly mutate:

- memory
- Git
- sandbox execution
- RAG indexes

### Rule 2: Services Own Their State

State ownership:

| State | Owner |
| --- | --- |
| task orchestration state | `anubis-core` or external task store |
| vector/memory records | `anubis-memory` |
| retrieval caches | `anubis-rag` |
| repository/worktree state | `anubis-git` |
| command execution state | `anubis-sandbox` |
| user session/display state | `anubis-ui` |

### Rule 3: Synchronous for Commands, Events for Updates

Use HTTP for direct commands:

- create task
- retrieve memory
- build context
- inspect Git diff
- start sandbox command

Use events for:

- task progress
- command output
- sandbox status
- Git workflow status
- memory write notification
- SOC/security alerts

### Rule 4: Idempotency on Mutating Calls

Every mutating request must include:

```text
idempotency_key
trace_id
task_id
actor
```

This allows retries without duplicate side effects.

### Rule 5: Timeouts and Retries Are Explicit

Default timeouts:

| Call | Timeout |
| --- | ---: |
| core -> memory read/write | 500 ms to 2 s |
| core -> rag context | 2 s to 5 s |
| core -> git status/diff | 1 s to 5 s |
| core -> git commit/PR | 10 s to 60 s |
| core -> sandbox validate | 500 ms |
| core -> sandbox command start | 2 s |
| sandbox stream events | long-lived |

Retry policy:

- retry idempotent reads
- retry idempotent writes only with idempotency keys
- do not retry Git commits blindly
- do not retry sandbox commands blindly
- retry event publish with bounded backoff

## API Boundaries Per Service

## anubis-core

Purpose:

Control-plane orchestration API.

Inbound from:

- `anubis-ui`
- future CLI/API clients

Outbound to:

- `anubis-memory`
- `anubis-rag`
- `anubis-git`
- `anubis-sandbox`
- optional event bus

API:

```text
POST /v1/tasks
GET  /v1/tasks/{task_id}
GET  /v1/tasks/{task_id}/events
POST /v1/tasks/{task_id}/approve
POST /v1/tasks/{task_id}/cancel
POST /v1/tasks/{task_id}/review
GET  /v1/health/live
GET  /v1/health/ready
```

Task create request:

```json
{
  "request_id": "req_...",
  "idempotency_key": "idem_...",
  "actor": "user",
  "source": "ui",
  "objective": "Refactor duplicated memory systems",
  "workspace_id": "workspace_anubis",
  "context": {}
}
```

Task response:

```json
{
  "task_id": "task_...",
  "trace_id": "trace_...",
  "status": "queued",
  "events_url": "/v1/tasks/task_.../events"
}
```

Failure behavior:

- if RAG is unavailable, task can start with degraded/no retrieved context only if policy allows
- if memory is unavailable, task should fail readiness for stateful operations
- if sandbox is unavailable, task may plan but cannot execute
- if Git is unavailable, Git workflow actions are disabled

## anubis-memory

Purpose:

Memory and vector persistence boundary.

Inbound from:

- `anubis-core`
- `anubis-rag`

Backend:

- Qdrant API for vector storage
- optional metadata wrapper store

API:

```text
POST /v1/memory/records
GET  /v1/memory/records/{record_id}
POST /v1/memory/query
POST /v1/memory/vector/upsert
POST /v1/memory/vector/search
GET  /v1/memory/snapshot
GET  /v1/health/live
GET  /v1/health/ready
```

Core write:

```json
{
  "idempotency_key": "idem_...",
  "trace_id": "trace_...",
  "task_id": "task_...",
  "actor": "anubis-core",
  "collection": "anubis_conversation_memory",
  "record": {
    "kind": "episode",
    "content_type": "summary",
    "content": "Task planned and sandbox validation passed.",
    "scope": "task",
    "scope_id": "task_...",
    "sensitivity": "internal",
    "metadata": {}
  },
  "index": true
}
```

Response:

```json
{
  "record_id": "mem_...",
  "vector_id": "vec_...",
  "collection": "anubis_conversation_memory",
  "indexed": true
}
```

Failure behavior:

- writes are idempotent by key
- raw secrets are rejected
- duplicate indexing is prevented by content hash or source id
- Qdrant unavailable means memory readiness is degraded/not ready

## anubis-rag

Purpose:

Retrieval, context building, ranking, and compression.

Inbound from:

- `anubis-core`

Outbound to:

- `anubis-memory`

API:

```text
POST /v1/rag/context
POST /v1/rag/query
POST /v1/rag/index/repository
POST /v1/rag/index/conversation
POST /v1/rag/chunks/deduplicate
GET  /v1/rag/cache/stats
GET  /v1/health/live
GET  /v1/health/ready
```

Context request:

```json
{
  "trace_id": "trace_...",
  "task_id": "task_...",
  "workspace_id": "workspace_anubis",
  "objective": "Refactor duplicated memory systems",
  "budget": {
    "max_files": 5,
    "max_tokens": 12000
  },
  "filters": {
    "subsystems": ["memory", "retrieval"]
  }
}
```

Context response:

```json
{
  "context_id": "ctx_...",
  "selected_files": [
    {
      "path": "core/memory/memory_manager.py",
      "rank": 1,
      "reason": "Canonical active memory manager"
    }
  ],
  "memory_refs": ["mem_..."],
  "token_estimate": 8200,
  "compression_applied": true
}
```

Failure behavior:

- if memory query fails, return degraded context with repository-only ranking when possible
- cache misses are not failures
- timeout returns partial context only if marked `partial: true`

## anubis-git

Purpose:

Repository status, branch, diff, commit, and PR engine.

Inbound from:

- `anubis-core`

Outbound:

- remote Git provider only after explicit approval/network permission
- optional event bus

API:

```text
GET  /v1/git/status
POST /v1/git/branches
GET  /v1/git/diff
POST /v1/git/stage
POST /v1/git/commit/draft
POST /v1/git/commit
POST /v1/git/pr/draft
POST /v1/git/pr/create
GET  /v1/git/pr/{pr_id}/status
GET  /v1/health/live
GET  /v1/health/ready
```

Trigger model:

Core triggers Git actions only after policy checks:

```text
UI request
  -> core approval/policy
     -> git status/diff/branch/commit/PR call
```

Branch request:

```json
{
  "idempotency_key": "idem_...",
  "trace_id": "trace_...",
  "task_id": "task_...",
  "workspace_id": "workspace_anubis",
  "base": "main",
  "branch": "anubis/feature/context-builder",
  "mode": "worktree"
}
```

Failure behavior:

- read operations may retry
- commit operation is idempotent by staged tree hash + idempotency key
- PR creation is idempotent by branch + provider + idempotency key
- force push disabled by default
- network/provider failure returns `blocked` or `retryable` status

## anubis-sandbox

Purpose:

Sandbox validation and isolated execution boundary.

Inbound from:

- `anubis-core`

Outbound:

- event stream to core
- optional event bus
- no direct UI communication for mutating actions

API:

```text
POST /v1/sandbox/validate
POST /v1/sandbox/commands
GET  /v1/sandbox/commands/{command_id}
GET  /v1/sandbox/commands/{command_id}/stream
POST /v1/sandbox/commands/{command_id}/cancel
GET  /v1/sandbox/profiles
GET  /v1/health/live
GET  /v1/health/ready
```

Command request:

```json
{
  "idempotency_key": "idem_...",
  "trace_id": "trace_...",
  "task_id": "task_...",
  "actor": "anubis-core",
  "profile": "test-runner",
  "cwd": "/workspace",
  "argv": ["python3", "-m", "compileall", "core", "src"],
  "limits": {
    "timeout_ms": 30000,
    "memory_mb": 256,
    "pids": 128
  },
  "network": "disabled",
  "filesystem": "scratch_or_readonly_workspace"
}
```

Command response:

```json
{
  "command_id": "cmd_...",
  "status": "queued",
  "stream_url": "/v1/sandbox/commands/cmd_.../stream"
}
```

Stream event:

```json
{
  "event_id": "evt_...",
  "sequence": 42,
  "command_id": "cmd_...",
  "type": "stdout",
  "payload": "PASS test_core_memory.py\n",
  "timestamp": "2026-06-05T12:00:00Z"
}
```

Failure behavior:

- command start is not retried unless idempotency key proves command was never started
- running commands survive transient core disconnect where possible
- output stream supports reconnect with `last_event_id`
- command results are persisted as execution evidence

## anubis-ui

Purpose:

User interface and streaming update consumer.

Inbound from:

- browser

Outbound to:

- `anubis-core`

UI update protocol:

```text
HTTP for commands
SSE for task/status streams
WebSocket only for interactive terminal input/output
```

API from browser to UI:

```text
GET  /
POST /api/tasks
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/events
POST /api/tasks/{task_id}/approve
POST /api/tasks/{task_id}/cancel
WS   /api/terminal/{command_id}
```

UI receives updates by subscribing to core:

```text
browser -> anubis-ui -> anubis-core /v1/tasks/{task_id}/events
```

SSE event types:

```text
task.created
task.planned
context.selected
git.status.updated
git.diff.ready
sandbox.command.started
sandbox.command.output
sandbox.command.completed
memory.record.created
review.completed
task.completed
task.failed
approval.required
```

Failure behavior:

- browser reconnects SSE with `Last-Event-ID`
- UI does not own task state
- UI can show stale cached status but must refresh from core

## Event Flow Model

## Minimal First Phase: Core Event Log + SSE

In the first phase, `anubis-core` owns task event ordering.

```text
service response/event
  -> anubis-core event log
     -> task SSE stream
        -> anubis-ui
```

Task event model:

```text
TaskEvent
  event_id
  sequence
  trace_id
  task_id
  source_service
  event_type
  status
  payload
  timestamp
```

Ordering:

- ordered per `task_id`
- globally unordered across tasks
- monotonic `sequence` inside each task stream

## Optional Second Phase: NATS Event Bus

Add NATS when asynchronous fanout and replay become necessary.

Recommended subjects:

```text
task.created
task.planned
task.completed
task.failed
memory.record.created
memory.record.indexed
rag.context.ready
git.status.updated
git.diff.ready
git.commit.created
git.pr.created
sandbox.command.started
sandbox.command.output
sandbox.command.completed
sandbox.command.failed
approval.required
audit.record.created
soc.alert.created
```

Event bus topology:

```text
anubis-core
  publishes: task.*, approval.*, audit.*
  subscribes: rag.*, git.*, sandbox.*, memory.*

anubis-memory
  publishes: memory.*
  subscribes: none initially

anubis-rag
  publishes: rag.*
  subscribes: memory.record.indexed optionally

anubis-git
  publishes: git.*
  subscribes: git.command.* optionally

anubis-sandbox
  publishes: sandbox.*
  subscribes: sandbox.command.* optionally

anubis-ui
  does not subscribe directly in phase 1
  receives events through core/UI gateway
```

Use JetStream only for:

- task lifecycle
- audit/security events
- sandbox command lifecycle
- Git publication events

Do not persist every stdout chunk forever by default. Persist command summaries and bounded logs.

## Redis Alternative

Redis Streams is acceptable if operational simplicity matters more than NATS subject routing.

Use Redis Streams for:

- `tasks:{task_id}:events`
- `sandbox:{command_id}:events`
- `alerts`

Tradeoff:

- Redis is familiar and simple
- NATS has cleaner pub/sub semantics and better subject routing

Recommendation:

```text
Start without a broker.
Add NATS JetStream before multi-core task ownership or SOC fanout.
Use Redis only if the team already operates Redis.
```

## Failure Tolerance Patterns

### Circuit Breakers

Core maintains circuit breakers for:

- memory
- rag
- git
- sandbox

States:

```text
closed
open
half_open
```

Behavior:

- RAG open: continue with reduced context if allowed
- Git open: disable Git actions
- Sandbox open: disable execution actions
- Memory open: reject stateful tasks or run read-only planning only

### Bulkheads

Separate pools:

- RAG calls
- Git calls
- sandbox execution calls
- memory writes
- UI event streaming

Reason:

Slow sandbox output must not starve core task creation.

### Idempotency

Required on:

- memory writes
- RAG indexing
- branch creation
- staging operations
- commit creation
- PR creation
- sandbox command creation

### Backpressure

Backpressure rules:

- cap active sandbox commands
- cap active Git mutations
- cap RAG context builds per core replica
- bound UI stream buffers
- drop or summarize excessive stdout chunks after persistence policy threshold

### Reconnect and Replay

SSE:

- client sends `Last-Event-ID`
- core replays from task event log

Sandbox streams:

- support `after_sequence`
- replay bounded output buffer
- return summary if output expired

Event bus:

- JetStream durable consumers for core/SOC
- ephemeral consumers for UI fanout

## Latency Targets

| Flow | Target |
| --- | ---: |
| UI command -> core ack | `<100 ms` |
| core -> memory write | `<250 ms` local p95 |
| core -> RAG context first response | `<2 s` |
| core -> Git status | `<500 ms` |
| core -> sandbox validate | `<100 ms` |
| sandbox stdout chunk -> UI | `<100 ms` |
| task event -> UI SSE | `<100 ms` |

## Recommended Protocol Decisions

| Boundary | Protocol | Reason |
| --- | --- | --- |
| UI -> Core | HTTP/JSON + SSE | Simple, browser-native, low operational overhead. |
| Core -> Memory | HTTP/JSON to wrapper or Qdrant REST | Simple and adequate for current vector/memory operations. |
| RAG -> Memory | HTTP/JSON or Qdrant REST/gRPC | REST first; gRPC if batch vector calls become hot. |
| Core -> RAG | HTTP/JSON | Context requests are structured and not streaming initially. |
| Core -> Git | HTTP/JSON | Git actions are command-like and approval-gated. |
| Core -> Sandbox | HTTP/JSON + SSE | Command creation is request/response; output is streaming. |
| Sandbox -> UI | via Core SSE/WebSocket gateway | Keeps UI from bypassing control plane. |
| Async events | none initially, NATS later | Avoid broker until fanout/replay needs justify it. |

## Final Design Contract

```text
Core talks to memory:
  HTTP/JSON memory API or Qdrant REST through memory wrapper,
  idempotent writes, access policy enforced by memory.

Core talks to RAG:
  HTTP/JSON context/query API,
  RAG queries memory and returns compressed context packets.

Git engine is triggered:
  UI requests action -> core policy/approval -> core calls git HTTP API,
  Git emits status/diff/commit/PR events back to core.

Sandbox executes tasks:
  core creates sandbox command through HTTP,
  sandbox enforces profile and streams output,
  core persists evidence and relays events to UI.

UI receives updates:
  browser uses HTTP for commands and SSE for task events,
  WebSocket reserved for interactive terminal sessions.

Event model:
  core-owned per-task event log first,
  optional NATS JetStream later for async fanout, replay, SOC, and multi-core ownership.
```

This communication model keeps ANUBIS low-latency and easy to operate now, while leaving a clean path to event-driven scale once service volume and failure recovery needs grow.
