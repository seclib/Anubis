# Anubis OS Production Architecture

```text
                         +------------------------------+
                         |        DESKTOP APP           |
                         |   Tauri + React Workspace    |
                         |                              |
                         | - Chat Interface             |
                         | - Notes / Workspace          |
                         | - Memory Viewer              |
                         | - Tool Logs UI               |
                         +--------------+---------------+
                                        |
                                        | HTTP / IPC
                                        v
+--------------------------------------------------------------------+
|                     AI CORE ORCHESTRATOR                           |
|                    FastAPI Central Brain                           |
|                                                                    |
|  Handles:                                                          |
|  - Multi-agent system: Planner / Executor / Critic                 |
|  - Deterministic agent loop                                        |
|  - Tool routing                                                    |
|  - Memory decisions                                                |
|  - Conversation state                                              |
+---------------+-------------------------------+--------------------+
                |                               |
                v                               v

+------------------------------+   +------------------------------+
|     AGENT SYSTEM CORE        |   |       MEMORY SYSTEM          |
|                              |   |                              |
|  +------------+              |   |  Short-term Memory           |
|  |  PLANNER   |              |   |  - session state cache       |
|  +-----+------+              |   |  - Redis optional            |
|        v                     |   |                              |
|  +------------+              |   |  Long-term Memory            |
|  | EXECUTOR   +--------------+-->|  - Qdrant Vector DB          |
|  +-----+------+              |   |  - embeddings store          |
|        v                     |   |                              |
|  +------------+              |   |  Ingestion Pipeline          |
|  |  CRITIC    |              |   |  - markdown/docs/chats       |
|  +------------+              |   |                              |
+---------------+--------------+   +---------------+--------------+
                |                                  |
                v                                  v

        +------------------------------------------------+
        |           TOOL ORCHESTRATION LAYER             |
        |                                                |
        |  - Tool Dispatcher                             |
        |  - Schema Validator                            |
        |  - Permission Checker                          |
        |                                                |
        |  Tools:                                        |
        |   - web_search                                 |
        |   - file_read                                  |
        |   - file_write                                 |
        |   - rag_query                                  |
        |   - memory_store                               |
        +----------------+-------------------------------+
                         |
                         v

        +------------------------------------------------+
        |            SANDBOX EXECUTION LAYER             |
        |                                                |
        |  Security Firewall                             |
        |  - input validation                            |
        |  - permission enforcement                      |
        |  - request_id tracking                         |
        |                                                |
        |  Isolated Runtime                              |
        |  - hardened tool-runner container              |
        |  - no host filesystem access                   |
        |  - CPU / memory limits                         |
        |                                                |
        |  Audit Logger                                  |
        |  - immutable hash-chained logs                 |
        |  - execution trace                             |
        |  - output hashing                              |
        +----------------+-------------------------------+
                         |
                         v

        +------------------------------------------------+
        |                INFRA LAYER                     |
        |                                                |
        |  - Docker Compose / Kubernetes-ready           |
        |  - Qdrant vector DB                            |
        |  - Redis cache/session                         |
        |  - AI Core service                             |
        |  - RAG service                                 |
        |  - Tool Runner service                         |
        +------------------------------------------------+
```

## Runtime Ownership

| Layer | Runtime | Code |
| --- | --- | --- |
| Desktop App | Tauri + React | `apps/desktop` |
| AI Core Orchestrator | FastAPI | `services/ai-core` |
| Agent System Core | Python modules | `services/ai-core/src/anubis_ai_core/agent`, `services/ai-core/src/anubis_ai_core/orchestrator` |
| Memory System | FastAPI + packages | `services/rag`, `packages/memory-sdk` |
| Tool Orchestration | FastAPI + Python registry | `services/tools/src/anubis_tools/core` |
| Sandbox Execution | Hardened tool runner | `services/tools/src/anubis_tools/sandbox` |
| Infra Layer | Docker Compose | `infra/docker`, `infra/env`, `infra/scripts` |

## Service Ports

| Service | Internal URL | Purpose |
| --- | --- | --- |
| AI Core | `http://ai-core:8000` | orchestration, chat, agents |
| RAG | `http://rag-service:8001` | ingestion and semantic retrieval |
| Tool Runner | `http://tool-runner:8002` | validated sandboxed tool execution |
| Qdrant | `http://qdrant:6333` | vector memory |
| Redis | `redis://redis:6379` | optional session/cache backend |

## Control Plane APIs

```text
POST /v1/chat
POST /v1/agent/run
POST /v1/orchestrator/run
GET  /v1/tools
```

## Data Plane APIs

```text
RAG:
POST /ingest
POST /search
POST /query

Tool Runner:
POST /v1/tools/execute
POST /v1/tools/secure-execute
```

## Security Boundaries

```text
Desktop cannot access tools directly.
AI Core cannot access host filesystem directly.
Agents cannot call tools except through ToolDispatcher.
Tool Runner cannot execute shell commands.
Tool Runner writes only to /workspace/sandbox and /var/log/anubis.
Tool audit logs are persisted on the tool_audit volume.
Qdrant and Redis are internal network services.
```

## Request Flow

```text
Desktop request
  -> AI Core request middleware assigns request_id
  -> Session Manager creates or resumes conversation session
  -> Planner creates strict JSON plan
  -> Execution Plan JSON DAG is validated
  -> Executor follows plan and calls ToolDispatcher
  -> ToolDispatcher sends canonical tool request to Tool Runtime Sandbox
  -> RAG / Memory retrieval runs when planned
  -> Tool Runner validates schema and permissions
  -> Sandbox executor runs approved tool
  -> Output sanitizer strips sensitive data
  -> Audit logger appends hash-chained event
  -> Critic validates executor output
  -> Critic approves or loops back to Executor
  -> AI Core emits final structured response
  -> Memory Write Decision runs without automatic write
```

## Production Invariants

```text
All LLM outputs are schema validated.
All tool inputs are schema validated.
All tool outputs are sanitized before agent use.
All agent stages emit trace events.
All sandbox executions emit audit events.
No tool has shell permission.
No wildcard filesystem permission exists.
No hardcoded user-specific host paths are required.
```
