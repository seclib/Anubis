#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/tauri_clean_artifacts.sh

echo "Removing reinstallable Node dependencies..."
rm -rf node_modules desktop-ui/node_modules

echo "Done. Reinstall Node dependencies with npm ci."
