#!/usr/bin/env sh
set -eu

ENV_FILE="${ANUBIS_ENV_FILE:-infra/env/.env}"

docker compose \
  --env-file "$ENV_FILE" \
  -f infra/docker/docker-compose.distributed.yml \
  up -d --build
