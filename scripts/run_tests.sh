#!/usr/bin/env sh
set -eu
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${PYTHONPATH:-}:src" python3 scripts/run_tests.py
