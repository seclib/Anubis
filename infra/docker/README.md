# ANUBIS Multi-Service Docker Build Strategy

Date: 2026-06-05

This directory contains production-only Dockerfile contracts for the target Docker Swarm
service split:

```text
infra/docker/
├── README.md
├── anubis-core/Dockerfile
├── anubis-rag/Dockerfile
├── anubis-memory/Dockerfile
├── anubis-git/Dockerfile
├── anubis-sandbox/Dockerfile
└── anubis-ui/Dockerfile
```

## Current Constraint

The repository currently implements a Python CLI/runtime, not HTTP microservice
entrypoints. These Dockerfiles are therefore isolated image contracts. `anubis-core`
can run the current bootstrap path. The other service images validate and package
their runtime module subsets, then idle with an import-checked production command
until service API entrypoints are implemented.

No application code is changed by these Dockerfiles.

## Build Commands

Build from the repository root:

```bash
docker build -f infra/docker/anubis-core/Dockerfile -t anubis-core:local .
docker build -f infra/docker/anubis-rag/Dockerfile -t anubis-rag:local .
docker build -f infra/docker/anubis-memory/Dockerfile -t anubis-memory:local .
docker build -f infra/docker/anubis-git/Dockerfile -t anubis-git:local .
docker build -f infra/docker/anubis-sandbox/Dockerfile -t anubis-sandbox:local .
docker build -f infra/docker/anubis-ui/Dockerfile -t anubis-ui:local .
```

## Reproducibility

- Python images are pinned by digest through `PYTHON_IMAGE`.
- Runtime images install no dev tools and no optional `dev` dependencies.
- The project currently has no runtime Python package dependencies.
- Source copies are service-scoped instead of copying the whole repository.
- The root `.dockerignore` excludes tests, docs, tools, scripts, caches, logs, and bytecode.

## Image Size Strategy

- Multi-stage builds validate imports in a builder stage.
- Runtime stages copy only the service source subset.
- No package manager install is performed.
- Runtime users are non-root UID/GID `10001`.
- Python bytecode generation is disabled at runtime.
- UI uses Python standard-library static serving because no Node/Tauri/frontend app exists yet.

## Service Entry Point Migration

Target future commands:

```text
anubis-core     -> python3 -m anubis_services.core
anubis-rag      -> python3 -m anubis_services.rag
anubis-memory   -> python3 -m anubis_services.memory
anubis-git      -> python3 -m anubis_services.git
anubis-sandbox  -> python3 -m anubis_services.sandbox
anubis-ui       -> static frontend server or compiled desktop/web shell
```

Until those modules exist, the non-core images intentionally start an import-checked
idle process so Swarm image builds can be validated without inventing service code.
