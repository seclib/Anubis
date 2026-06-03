#!/usr/bin/env sh
set -eu

IMAGE="${ANUBIS_DISTRIBUTED_IMAGE:-anubis/distributed:${ANUBIS_IMAGE_TAG:-local}}"

docker build \
  -f infra/docker/Dockerfile.distributed \
  -t "$IMAGE" \
  .

printf '%s\n' "Built $IMAGE"
