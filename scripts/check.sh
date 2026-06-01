#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

"$PYTHON" -m compileall -q agent api app backend cli core executor intelligence knowledge llm memory monitoring rag retrieval runtime services storage tools workers
"$PYTHON" -m unittest discover -s tests -p 'test*.py'

if [[ -d desktop/node_modules ]]; then
  (cd desktop && npm run build)
else
  echo "desktop/node_modules not found; skipping desktop build"
fi
