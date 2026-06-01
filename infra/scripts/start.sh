#!/usr/bin/env sh
set -eu

# Usage:
#   infra/scripts/start.sh dev
#   infra/scripts/start.sh prod
# Defaults to dev. Copy infra/env/.env.example to infra/env/.env to override ports/config.

MODE="${1:-dev}"
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/infra/env/.env"

if [ ! -f "${ENV_FILE}" ]; then
  ENV_FILE="${ROOT_DIR}/infra/env/.env.example"
fi

cd "${ROOT_DIR}/infra/docker"

case "${MODE}" in
  dev)
    docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.dev.yml up --build
    ;;
  prod)
    docker compose --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.prod.yml up -d --build
    ;;
  *)
    echo "Unknown mode: ${MODE}. Expected dev or prod." >&2
    exit 2
    ;;
esac
