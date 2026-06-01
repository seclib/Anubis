#!/usr/bin/env sh
set -eu

# Checks published host endpoints and container health.
# Exits non-zero if any required service is unhealthy.

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/infra/env/.env"

if [ ! -f "${ENV_FILE}" ]; then
  ENV_FILE="${ROOT_DIR}/infra/env/.env.example"
fi

# shellcheck disable=SC1090
. "${ENV_FILE}"

AI_CORE_PORT="${AI_CORE_PORT:-8000}"
RAG_PORT="${RAG_PORT:-8001}"
TOOL_RUNNER_PORT="${TOOL_RUNNER_PORT:-8002}"
QDRANT_HTTP_PORT="${QDRANT_HTTP_PORT:-6333}"
REDIS_PORT="${REDIS_PORT:-6379}"

check_http() {
  name="$1"
  url="$2"
  python3 - "$url" <<'PY'
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=3) as response:
    if response.status >= 400:
        raise SystemExit(response.status)
PY
  echo "ok ${name} ${url}"
}

check_tcp() {
  name="$1"
  host="$2"
  port="$3"
  python3 - "$host" "$port" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.create_connection((host, port), timeout=3):
    pass
PY
  echo "ok ${name} ${host}:${port}"
}

check_http "ai-core" "http://127.0.0.1:${AI_CORE_PORT}/health"
check_http "rag-service" "http://127.0.0.1:${RAG_PORT}/health"
check_http "tool-runner" "http://127.0.0.1:${TOOL_RUNNER_PORT}/health"
check_tcp "qdrant" "127.0.0.1" "${QDRANT_HTTP_PORT}"
check_tcp "redis" "127.0.0.1" "${REDIS_PORT}"

cd "${ROOT_DIR}/infra/docker"
docker compose --env-file "${ENV_FILE}" -f docker-compose.yml ps
