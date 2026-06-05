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

mkdir -p state/security-tools/metasploit

echo "[anubis] starting optional security tools stack"
echo "[anubis] BloodHound UI binds to 127.0.0.1:${BLOODHOUND_HTTP_PORT:-8080}"
echo "[anubis] Metasploit and Neo4j ports are not published"

$COMPOSE --profile exploit-tools --profile graph-tools up -d metasploit bloodhound-neo4j bloodhound
