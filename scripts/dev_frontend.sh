#!/usr/bin/env bash
set -euo pipefail

URL="${ANUBIS_DEV_URL:-http://127.0.0.1:1420}"

if curl -fsS "$URL" >/dev/null 2>&1; then
  echo "ANUBIS frontend already running at $URL"
  while true; do
    sleep 3600
  done
fi

exec npm run dev
