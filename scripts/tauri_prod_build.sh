#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export NODE_ENV=production
export RUSTFLAGS="${RUSTFLAGS:-} -C strip=symbols"

bash scripts/tauri_clean_artifacts.sh

if [ ! -d node_modules ]; then
  npm ci
fi

npm run build
npm run tauri -- build

echo
echo "Production artifacts:"
find src-tauri/target/release/bundle -maxdepth 3 -type f -exec du -h {} + 2>/dev/null | sort -hr || true

echo
echo "Final size report:"
bash scripts/tauri_size_report.sh
