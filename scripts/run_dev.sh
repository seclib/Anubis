#!/usr/bin/env sh
set -eu
PYTHONPATH="${PYTHONPATH:-}:src" python3 bootstrap.py
