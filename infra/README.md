# ANUBIS DEVIN++ Production Infrastructure

This infrastructure prepares ANUBIS for distributed deployment on Docker Compose, Docker Swarm, or Kubernetes.

## Service Boundaries

- `api-gateway`: health/API ingress boundary for external callers.
- `company-runtime`: master autonomous company loop. Runs one active replica by default.
- `orchestrator`: coordinates task state and assignment.
- `planner`: stateless planning workers.
- `executor`: scalable execution workers with access to Git workspaces and sandbox volumes.
- `reviewer`: stateless validation/self-review workers.
- `tool-runner`: isolated tool execution boundary.
- `redis`: externalized execution state, queues, locks, and state-machine persistence.
- `qdrant`: externalized vector memory.
- `git_repos`: external Git workspace volume or mounted Git-backed storage.

## Stateless Design

Application services are designed to be stateless where possible. Runtime state must live in:

- Redis: task lifecycle, locks, queues, retry state.
- Qdrant: vector memory and retrieval indexes.
- Git remotes/volumes: repository state and generated branches.
- Tool audit volume: execution audit log.

Only `redis`, `qdrant`, and workspace/audit volumes require persistent storage.

## Docker Compose

```bash
docker compose \
  --env-file infra/env/.env \
  -f infra/docker/docker-compose.distributed.yml \
  up -d --build
```

Enable the master loop after verifying health:

```bash
ANUBIS_COMPANY_RUNTIME_ENABLED=true docker compose \
  --env-file infra/env/.env \
  -f infra/docker/docker-compose.distributed.yml \
  up -d company-runtime
```

## Docker Swarm

```bash
docker build -f infra/docker/Dockerfile.distributed -t anubis/distributed:latest .
docker stack deploy -c infra/swarm/anubis-stack.yml anubis
```

For stateful placement, label at least one node:

```bash
docker node update --label-add anubis.stateful=true <node>
```

## Kubernetes

Build/push the image first:

```bash
docker build -f infra/docker/Dockerfile.distributed -t registry.example.com/anubis/distributed:latest .
docker push registry.example.com/anubis/distributed:latest
```

Then set the image and apply:

```bash
kustomize build infra/k8s/base | \
  sed 's#anubis/distributed:latest#registry.example.com/anubis/distributed:latest#g' | \
  kubectl apply -f -
```

Do not commit real secrets. Replace `infra/k8s/base/secret.example.yaml` with a cluster-managed Secret.

## Health

Every distributed service exposes:

- `GET /health`
- `GET /ready`

Default internal port: `8080`.

## Safety Defaults

- Company runtime loop starts paused unless `ANUBIS_COMPANY_RUNTIME_ENABLED=true`.
- High-risk continuous-improvement tasks are skipped by default.
- Tool-runner and stateless services drop Linux capabilities.
- Redis/Qdrant/Git are externalized state boundaries.
