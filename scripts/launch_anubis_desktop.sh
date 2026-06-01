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

if [[ -n "${ANUBIS_EXEC:-}" ]]; then
  exec "$ANUBIS_EXEC"
fi

for candidate in \
  "$repo_root/desktop/src-tauri/target/release/anubis-desktop" \
  "$repo_root/desktop/src-tauri/target/debug/anubis-desktop" \
  "$repo_root/target/release/anubis-desktop" \
  "$repo_root/target/debug/anubis-desktop"
do
  if [[ -x "$candidate" ]]; then
    exec "$candidate"
  fi
done

if command -v cargo >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  cd "$repo_root/desktop"
  exec cargo tauri dev
fi

if command -v notify-send >/dev/null 2>&1; then
  notify-send "Anubis Desktop OS" "No built launcher was found. Build it with: cd desktop && cargo tauri build"
fi

printf 'Anubis Desktop OS launcher not found.\n' >&2
printf 'Build it with: cd %s/desktop && cargo tauri build\n' "$repo_root" >&2
exit 1
