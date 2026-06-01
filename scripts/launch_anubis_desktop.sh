#!/usr/bin/env bash
set -euo pipefail

resolve_repo_root() {
  if [[ -n "${ANUBIS_INSTALL_DIR:-}" ]]; then
    printf '%s\n' "$ANUBIS_INSTALL_DIR"
    return
  fi

  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir/.." && pwd
}

repo_root="$(resolve_repo_root)"
cd "$repo_root"

install_frontend_dependencies() {
  # Ensure we are in the desktop project directory where package.json resides
  local prev_dir="$(pwd)"
  cd "$repo_root/desktop"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
  cd "$prev_dir"
}

ensure_frontend_ready() {
  cd "$repo_root/desktop"

  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || printf '0')"
  if ((node_major < 20)); then
    printf 'Anubis Desktop requires Node.js 20 or newer. Found: %s\n' "$(node --version 2>/dev/null || printf 'missing')" >&2
    return 1
  fi

  if [[ ! -d node_modules ]]; then
    printf '[Anubis] Installing frontend dependencies...\n'
    install_frontend_dependencies
  fi

  if ! node -e "require.resolve('vite/package.json')" >/dev/null 2>&1; then
    printf '[Anubis] Vite is missing; reinstalling frontend dependencies...\n'
    install_frontend_dependencies
  fi

  if [[ "$(npm pkg get scripts.dev 2>/dev/null)" == "undefined" ]]; then
    printf 'Anubis Desktop package.json is missing scripts.dev\n' >&2
    return 1
  fi

  if [[ "$(npm pkg get scripts.tauri 2>/dev/null)" == "undefined" ]]; then
    printf 'Anubis Desktop package.json is missing scripts.tauri\n' >&2
    return 1
  fi
}

if [[ -n "${ANUBIS_EXEC:-}" ]]; then
  exec "$ANUBIS_EXEC"
fi

for candidate in \
  "$repo_root/desktop/src-tauri/target/release/anubis-desktop" \
  "$repo_root/target/release/anubis-desktop"
do
  if [[ -x "$candidate" ]]; then
    exec "$candidate"
  fi
done

  if command -v cargo >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
    ensure_frontend_ready
    # Use the dedicated tauri-dev script which runs both Vite dev server and Tauri in dev mode
    exec npm run tauri-dev
  fi

if command -v notify-send >/dev/null 2>&1; then
  notify-send "Anubis Desktop OS" "No built launcher was found. Build it with: cd desktop && cargo tauri build"
fi

printf 'Anubis Desktop OS launcher not found.\n' >&2
printf 'Build it with: cd %s/desktop && cargo tauri build\n' "$repo_root" >&2
exit 1
