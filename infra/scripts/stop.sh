#!/usr/bin/env sh
set -eu

# Usage:
#   infra/scripts/stop.sh
#   infra/scripts/stop.sh --volumes   # removes persistent volumes; data loss by design.

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/infra/env/.env"
VOLUME_FLAG=""

if [ ! -f "${ENV_FILE}" ]; then
  ENV_FILE="${ROOT_DIR}/infra/env/.env.example"
fi

if [ "${1:-}" = "--volumes" ]; then
  VOLUME_FLAG="-v"
fi

cd "${ROOT_DIR}/infra/docker"
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.prod.yml down ${VOLUME_FLAG}
