# ANUBIS Docker Swarm Production Stack

Date: 2026-06-05

## Stack File

Production stack file:

```text
docker-stack.yml
```

Deploy:

```bash
docker stack deploy -c docker-stack.yml anubis
```

Required node labels before deploy:

```bash
docker node update --label-add anubis.memory=true <memory-node>
docker node update --label-add anubis.git=true <git-node>
```

## Network Topology

```text
                         published :8080
                              │
                      ┌───────▼────────┐
                      │   anubis-ui    │
                      │ public + ctrl  │
                      └───────┬────────┘
                              │ anubis-control
                              │ internal encrypted overlay
                      ┌───────▼────────┐
                      │  anubis-core   │
                      │ stateless API  │
                      └───┬────────┬───┘
                          │        │
             anubis-data  │        │ anubis-execution
  internal encrypted      │        │ internal encrypted
                          │        │
          ┌───────────────▼──┐   ┌─▼────────────┐
          │   anubis-rag     │   │ anubis-git   │
          │ retrieval worker │   │ repo engine  │
          └──────────┬───────┘   └──────────────┘
                     │
          ┌──────────▼──────────┐
          │    anubis-memory    │
          │ Qdrant + volume     │
          └─────────────────────┘

                      ┌────────────────┐
                      │ anubis-sandbox │
                      │ isolated exec  │
                      └────────────────┘
                         anubis-execution only
```

Networks:

| Network | Type | Members | Purpose |
| --- | --- | --- | --- |
| `anubis-public` | encrypted overlay | `anubis-ui` | UI ingress only. |
| `anubis-control` | internal encrypted overlay | `anubis-ui`, `anubis-core` | UI-to-core API traffic. |
| `anubis-data` | internal encrypted overlay | `anubis-core`, `anubis-rag`, `anubis-memory` | Retrieval and Qdrant traffic. |
| `anubis-execution` | internal encrypted overlay | `anubis-core`, `anubis-git`, `anubis-sandbox` | Git and sandbox control traffic. |

Only `anubis-ui` publishes a host port. All other communication is internal overlay traffic.

## Service Scaling Strategy

| Service | Default Replicas | Scaling Strategy |
| --- | ---: | --- |
| `anubis-ui` | 2 | Scale horizontally behind Swarm ingress. Stateless static/service UI. |
| `anubis-core` | 2 | Stateless by design. Scale once task/session state is externalized. |
| `anubis-memory` | 1 | Stateful Qdrant with persistent volume. Scale only after enabling Qdrant clustering/sharding. |
| `anubis-rag` | 2 | Scale horizontally; keep per-replica caches disposable. |
| `anubis-git` | 1 | Scale per workspace/repository shard, not blindly, because it owns workspace volume state. |
| `anubis-sandbox` | 2 | Scale horizontally for isolated execution capacity. No host mounts, no shared sandbox filesystem. |

Recommended commands:

```bash
docker service scale anubis_anubis-ui=3
docker service scale anubis_anubis-core=3
docker service scale anubis_anubis-rag=4
docker service scale anubis_anubis-sandbox=4
```

Do not scale `anubis-memory` above `1` until Qdrant clustering is configured. Do not scale `anubis-git` above `1` for a single workspace volume.

## Failure Isolation Strategy

### UI Failure

Impact:

- User access degrades only if all UI replicas fail.

Isolation:

- UI has no memory, Git, or sandbox volume.
- UI can be restarted or rolled back independently.

### Core Failure

Impact:

- New orchestration requests fail while core replicas are unavailable.
- Persistent memory remains safe in Qdrant.

Isolation:

- Core is stateless and has no volumes.
- Core does not execute shell commands directly.
- Rolling update uses `start-first` and rollback on failure.

### Memory/Qdrant Failure

Impact:

- Memory and vector retrieval unavailable.
- Core/RAG should degrade or fail readiness.

Isolation:

- Qdrant data is isolated to `anubis-qdrant-data`.
- Only data-network services can reach Qdrant.
- Placement label keeps stateful storage on known nodes.

### RAG Failure

Impact:

- Context retrieval degrades.
- Core can still reject/queue tasks or run non-RAG flows depending on future API behavior.

Isolation:

- RAG is stateless.
- No persistent volume.
- Scale or restart independently.

### Git Failure

Impact:

- Branch/diff/commit/PR functions unavailable.
- Core and memory remain unaffected.

Isolation:

- Git workspace volume is mounted only into `anubis-git`.
- No public ingress.
- Network disabled by service environment except future approved workflows.

### Sandbox Failure

Impact:

- Command/test execution unavailable.
- Core can continue planning/review flows.

Isolation:

- No host mounts.
- No Docker socket.
- Read-only root filesystem.
- Dropped capabilities.
- Private execution network only.
- Ephemeral tmpfs only.

## Strict Isolation Rules

- No monolithic `anubis` service exists in the stack.
- Only `anubis-ui` publishes a port.
- `anubis-core` has no persistent volume and is stateless.
- `anubis-memory` is the only service with the Qdrant persistence volume.
- `anubis-git` owns its workspace volume; it is not shared with core or sandbox.
- `anubis-sandbox` has no host filesystem mount and no shared workspace volume.
- Backend networks are `internal: true`.
- Overlay networks are encrypted.
- Python services run as UID/GID `10001`.
- Python services use read-only root filesystems, dropped capabilities, and `no-new-privileges`.

## Current Implementation Note

The current repository does not yet implement long-running HTTP API servers for every service. The stack uses the service images created under `infra/docker/` as production image contracts. `anubis-core` is overridden to run an import-checked stateless process instead of the current one-shot CLI bootstrap. Replace those commands with real service entrypoints as the microservice APIs are implemented.
