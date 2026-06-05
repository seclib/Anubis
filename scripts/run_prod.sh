#!/usr/bin/env sh
set -eu
ANUBIS_ENV=production PYTHONPATH="${PYTHONPATH:-}:src" python3 bootstrap.py
