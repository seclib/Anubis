#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "docker compose is required" >&2
  exit 1
fi

echo "[anubis] stopping security tools stack"
$COMPOSE --profile exploit-tools --profile graph-tools stop metasploit bloodhound bloodhound-neo4j
