#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

exec "$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
