#!/usr/bin/env bash
set -euo pipefail

ANUBIS_OLLAMA_URL="${ANUBIS_OLLAMA_URL:-http://127.0.0.1:11434}"
ANUBIS_MODEL="${ANUBIS_MODEL:-qwen2.5-coder:7b}"
ANUBIS_MODE="dev"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  BOLD="$(printf '\033[1m')"
  DIM="$(printf '\033[2m')"
  RED="$(printf '\033[31m')"
  GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"
  BLUE="$(printf '\033[34m')"
  RESET="$(printf '\033[0m')"
else
  BOLD=""
  DIM=""
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  RESET=""
fi

print_banner() {
  printf '%s\n' "${BLUE}========================${RESET}"
  printf '%s\n' "${BOLD}   ANUBIS LAUNCHER${RESET}"
  printf '%s\n' "${BLUE}========================${RESET}"
  printf '%s\n' "Starting system..."
}

usage() {
  cat <<EOF
Usage: ./start-anubis.sh [--dev|--prod]

Options:
  --dev       Start the Tauri development runtime. Default.
  --prod      Build and launch the production Tauri binary.
  --help      Show this help message.

Environment:
  ANUBIS_OLLAMA_URL   Ollama URL. Default: http://127.0.0.1:11434
  ANUBIS_MODEL        Ollama model. Default: qwen2.5-coder:7b
  NO_COLOR            Disable colored terminal output.
EOF
}

detect_os() {
  local kernel
  kernel="$(uname -s 2>/dev/null || printf 'unknown')"

  case "$kernel" in
    Linux*) printf 'linux' ;;
    Darwin*) printf 'macos' ;;
    CYGWIN*|MINGW*|MSYS*) printf 'windows' ;;
    *) printf 'unknown' ;;
  esac
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dev)
        ANUBIS_MODE="dev"
        ;;
      --prod)
        ANUBIS_MODE="prod"
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        die "Unknown option: $1. Run ./start-anubis.sh --help"
        ;;
    esac
    shift
  done
}

log() {
  printf '%s %s\n' "${GREEN}[ANUBIS]${RESET}" "$1"
}

info() {
  printf '%s %s\n' "${BLUE}[ANUBIS]${RESET}" "$1"
}

warn() {
  printf '%s %s\n' "${YELLOW}[ANUBIS] Warning:${RESET}" "$1" >&2
}

die() {
  printf '%s %s\n' "${RED}[ANUBIS] Error:${RESET}" "$1" >&2
  exit 1
}

on_error() {
  local exit_code=$?
  printf '%s Launcher stopped unexpectedly at line %s. Exit code: %s\n' \
    "${RED}[ANUBIS] Error:${RESET}" "${BASH_LINENO[0]:-unknown}" "$exit_code" >&2
  printf '%s Re-run with ./start-anubis.sh --help or check the message above.\n' \
    "${DIM}[ANUBIS]${RESET}" >&2
  exit "$exit_code"
}

trap on_error ERR

run_checked() {
  local description="$1"
  shift

  info "$description"
  "$@" || die "$description failed."
}

find_release_binary() {
  local os_name="$1"

  case "$os_name" in
    windows)
      find src-tauri/target/release -maxdepth 2 -type f -name '*.exe' -perm -111 2>/dev/null | head -n 1
      ;;
    macos)
      find src-tauri/target/release -maxdepth 4 \( -type d -name '*.app' -o -type f -perm -111 \) 2>/dev/null | head -n 1
      ;;
    *)
      find src-tauri/target/release -maxdepth 2 -type f -perm -111 ! -name '*.so' ! -name '*.d' 2>/dev/null | head -n 1
      ;;
  esac
}

launch_release_binary() {
  local os_name="$1"
  local binary="$2"

  if [[ -z "$binary" ]]; then
    die "Production build completed, but no launchable release binary was found."
  fi

  log "Launching production binary: $binary"

  if [[ "$os_name" == "macos" && "$binary" == *.app ]]; then
    exec open "$binary"
  fi

  exec "$binary"
}

print_startup_context() {
  local os_name="$1"
  log "Mode: $ANUBIS_MODE"
  log "OS: $os_name"
  log "Project: $script_dir"
}

validate_os() {
  local os_name="$1"

  if [[ "$os_name" == "unknown" ]]; then
    warn "Could not detect OS. Continuing with generic Unix launch behavior."
  fi

  if [[ "$os_name" == "windows" ]]; then
    warn "Windows detected. This Bash launcher expects Git Bash, MSYS2, or WSL."
  fi
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    die "Missing required command: $command_name"
  fi
}

ensure_dependencies() {
  require_command node
  require_command npm
  require_command cargo
  require_command curl

  if [[ ! -f package.json ]]; then
    die "package.json not found. Run this launcher from the ANUBIS project root."
  fi

  if [[ ! -d node_modules ]]; then
    log "node_modules missing; installing frontend dependencies..."
    if [[ -f package-lock.json ]]; then
      run_checked "Installing dependencies with npm ci" npm ci
    else
      run_checked "Installing dependencies with npm install" npm install
    fi
  else
    log "Node dependencies found."
  fi
}

ollama_is_ready() {
  curl -fsS "$ANUBIS_OLLAMA_URL/api/tags" >/dev/null 2>&1
}

ensure_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama is not installed or not on PATH. Agent streaming will wait for $ANUBIS_OLLAMA_URL."
    return
  fi

  if ollama_is_ready; then
    log "Ollama is online at $ANUBIS_OLLAMA_URL."
  else
    log "Starting Ollama service..."
    nohup ollama serve > state/ollama.log 2>&1 &
    sleep 2

    if ollama_is_ready; then
      log "Ollama started."
    else
      warn "Could not confirm Ollama startup. Check state/ollama.log or run 'ollama serve' manually."
    fi
  fi

  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$ANUBIS_MODEL"; then
    log "Model ready: $ANUBIS_MODEL."
  else
    warn "Model '$ANUBIS_MODEL' is not installed. Run: ollama pull $ANUBIS_MODEL"
  fi
}

launch_dev() {
  log "Launching ANUBIS desktop..."
  log "Command: npm run tauri dev"
  exec npm run tauri dev
}

launch_prod() {
  local os_name="$1"

  log "Building ANUBIS production desktop..."
  log "Command: npm run tauri -- build"
  npm run tauri -- build

  launch_release_binary "$os_name" "$(find_release_binary "$os_name")"
}

main() {
  local os_name
  os_name="$(detect_os)"

  parse_args "$@"
  print_banner
  print_startup_context "$os_name"
  validate_os "$os_name"

  mkdir -p state
  ensure_dependencies
  ensure_ollama

  case "$ANUBIS_MODE" in
    dev) launch_dev ;;
    prod) launch_prod "$os_name" ;;
    *) die "Unsupported mode: $ANUBIS_MODE" ;;
  esac
}

main "$@"
mkdir -p state
ensure_dependencies
ensure_ollama
launch_tauri
