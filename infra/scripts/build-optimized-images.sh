#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

export DOCKER_BUILDKIT=1

docker build \
  --target runtime \
  -f Dockerfile \
  -t anubis-api:optimized \
  .

docker build \
  --target runtime \
  -f infra/docker/Dockerfile.core \
  -t anubis-core:optimized \
  .

docker build \
  --target runtime \
  -f infra/docker/Dockerfile.ml \
  --build-arg ML_REQUIREMENTS=requirements/ml.txt \
  -t anubis-ml:optimized \
  .

docker build \
  --target runtime \
  -f infra/docker/Dockerfile.tooling \
  -t anubis-tooling:optimized \
  .

docker image ls \
  anubis-api:optimized \
  anubis-core:optimized \
  anubis-ml:optimized \
  anubis-tooling:optimized
