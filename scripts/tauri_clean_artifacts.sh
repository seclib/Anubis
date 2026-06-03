#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Removing reinstallable Tauri/frontend build artifacts..."
rm -rf \
  src-tauri/target \
  runtime-tauri/target \
  dist \
  desktop-ui/dist \
  src-tauri/gen/schemas \
  runtime-tauri/gen/schemas \
  node_modules/.vite \
  desktop-ui/node_modules/.vite

find . -type d \( \
  -name .vite -o \
  -name .cache \
\) -prune -exec rm -rf {} +

echo "Done. Source, configs, lockfiles, and dependencies were preserved."
