#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "ANUBIS Tauri/frontend size report"
echo
du -sh \
  src-tauri \
  src-tauri/target \
  runtime-tauri \
  runtime-tauri/target \
  node_modules \
  desktop-ui/node_modules \
  dist \
  desktop-ui/dist \
  2>/dev/null || true

echo
echo "Largest build/dependency folders"
find . -maxdepth 4 -type d \( \
  -name node_modules -o \
  -name target -o \
  -name dist -o \
  -name build -o \
  -name .cache \
\) -prune -exec du -sh {} + 2>/dev/null | sort -hr

echo
echo "Largest non-cache static assets"
find src src-tauri desktop-ui -type f \( \
  -name '*.png' -o \
  -name '*.jpg' -o \
  -name '*.jpeg' -o \
  -name '*.webp' -o \
  -name '*.svg' -o \
  -name '*.ico' -o \
  -name '*.icns' -o \
  -name '*.mp4' -o \
  -name '*.wasm' \
\) -not -path '*/node_modules/*' -not -path '*/target/*' \
  -printf '%s\t%p\n' 2>/dev/null \
  | sort -nr \
  | head -40 \
  | awk '{ size=$1; $1=""; printf "%.2fM%s\n", size/1048576, $0 }'
