#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="Anubis Desktop OS"
LOG_FILE="${SETUP_LOG_FILE:-$ROOT_DIR/state/setup.log}"
INSTALL_SYSTEM="${INSTALL_SYSTEM:-auto}"
START_QDRANT="${START_QDRANT:-false}"
CONFIGURE_GIT="${CONFIGURE_GIT:-true}"
INSTALL_FRONTEND="${INSTALL_FRONTEND:-true}"

if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_BLUE=$'\033[34m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
else
  C_RESET=""
  C_BLUE=""
  C_GREEN=""
  C_YELLOW=""
  C_RED=""
fi

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --start-qdrant       Start local Qdrant and Redis with docker compose.
  --no-system          Do not install missing system packages.
  --no-frontend        Skip desktop npm dependencies.
  --no-git             Skip Git identity configuration.
  -h, --help           Show this help.

Environment:
  INSTALL_SYSTEM=auto|false
  START_QDRANT=true|false
  CONFIGURE_GIT=true|false
  INSTALL_FRONTEND=true|false
  SETUP_LOG_FILE=state/setup.log
EOF
}

while (($#)); do
  case "$1" in
    --start-qdrant)
      START_QDRANT="true"
      ;;
    --no-system)
      INSTALL_SYSTEM="false"
      ;;
    --no-frontend)
      INSTALL_FRONTEND="false"
      ;;
    --no-git)
      CONFIGURE_GIT="false"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

log() {
  local level="$1"
  local color="$2"
  shift 2
  local message="$*"
  printf '%s[%s]%s %s\n' "$color" "$level" "$C_RESET" "$message"
  printf '[%s] %s\n' "$level" "$message" >> "$LOG_FILE"
}

info() { log "INFO" "$C_BLUE" "$*"; }
ok() { log " OK " "$C_GREEN" "$*"; }
warn() { log "WARN" "$C_YELLOW" "$*"; }
fail() { log "FAIL" "$C_RED" "$*"; }

run() {
  info "$*"
  "$@" 2>&1 | tee -a "$LOG_FILE"
}

on_error() {
  local code=$?
  fail "Setup failed at line $1 with exit code $code. See $LOG_FILE"
  exit "$code"
}
trap 'on_error $LINENO' ERR

need_command() {
  command -v "$1" >/dev/null 2>&1
}

sudo_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif need_command sudo; then
    sudo "$@"
  else
    return 127
  fi
}

detect_package_manager() {
  if need_command apt-get; then
    echo "apt"
  elif need_command dnf; then
    echo "dnf"
  elif need_command pacman; then
    echo "pacman"
  else
    echo ""
  fi
}

install_packages() {
  local manager="$1"
  shift
  local packages=("$@")
  if ((${#packages[@]} == 0)); then
    return 0
  fi

  case "$manager" in
    apt)
      run sudo_cmd apt-get update
      run sudo_cmd apt-get install -y "${packages[@]}"
      ;;
    dnf)
      run sudo_cmd dnf install -y "${packages[@]}"
      ;;
    pacman)
      run sudo_cmd pacman -Sy --needed --noconfirm "${packages[@]}"
      ;;
    *)
      return 1
      ;;
  esac
}

install_system_dependencies() {
  if [[ "$INSTALL_SYSTEM" == "false" ]]; then
    warn "Skipping system package installation."
    return 0
  fi

  local manager
  manager="$(detect_package_manager)"
  if [[ -z "$manager" ]]; then
    warn "No supported package manager found. Install Python, pip, Node/npm, Docker, and Tauri Linux libraries manually."
    return 0
  fi

  local packages=()
  case "$manager" in
    apt)
      need_command python3 || packages+=(python3)
      python3 -m venv --help >/dev/null 2>&1 || packages+=(python3-venv)
      python3 -m pip --version >/dev/null 2>&1 || packages+=(python3-pip)
      need_command node || packages+=(nodejs)
      need_command npm || packages+=(npm)
      need_command git || packages+=(git)
      need_command docker || packages+=(docker.io docker-compose-plugin)
      packages+=(libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev)
      ;;
    dnf)
      need_command python3 || packages+=(python3)
      python3 -m pip --version >/dev/null 2>&1 || packages+=(python3-pip)
      need_command node || packages+=(nodejs npm)
      need_command git || packages+=(git)
      need_command docker || packages+=(docker docker-compose-plugin)
      packages+=(webkit2gtk4.1-devel javascriptcoregtk4.1-devel libsoup3-devel)
      ;;
    pacman)
      need_command python3 || packages+=(python)
      python3 -m pip --version >/dev/null 2>&1 || packages+=(python-pip)
      need_command node || packages+=(nodejs)
      need_command npm || packages+=(npm)
      need_command git || packages+=(git)
      need_command docker || packages+=(docker docker-compose)
      packages+=(webkit2gtk-4.1 libsoup3)
      ;;
  esac

  if ((${#packages[@]} == 0)); then
    ok "System dependencies already available."
    return 0
  fi

  info "Installing missing system packages with $manager: ${packages[*]}"
  if ! install_packages "$manager" "${packages[@]}"; then
    warn "System package installation failed or requires privileges. Continue after installing: ${packages[*]}"
  fi
}

setup_python() {
  if ! need_command python3; then
    fail "python3 is required but was not found."
    exit 1
  fi

  if [[ ! -d .venv ]]; then
    run python3 -m venv .venv
  else
    ok "Python virtual environment already exists."
  fi

  # shellcheck disable=SC1091
  . .venv/bin/activate
  run python -m pip install --upgrade pip
  run python -m pip install -r requirements.txt
  if [[ -f backend/requirements.txt ]]; then
    run python -m pip install -r backend/requirements.txt
  fi
  for package in \
    anubis/kernel \
    anubis/packages/prompt-engine \
    anubis/packages/memory-sdk \
    anubis/services/tools \
    anubis/services/rag \
    anubis/services/ai-core
  do
    if [[ -f "$package/pyproject.toml" ]]; then
      run python -m pip install -e "$package"
    fi
  done
  ok "Python backend dependencies installed."
}

setup_frontend() {
  if [[ "$INSTALL_FRONTEND" == "false" ]]; then
    warn "Skipping frontend dependencies."
    return 0
  fi

  if ! need_command npm; then
    warn "npm is not available. Desktop dependencies were not installed."
    return 0
  fi

  if ! need_command node; then
    warn "node is not available. Desktop dependencies were not installed."
    return 0
  fi

  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || printf '0')"
  if ((node_major < 20)); then
    warn "Node.js 20 or newer is required for Vite/Tauri. Found: $(node --version)"
    return 0
  fi

  if [[ -f desktop/package-lock.json ]]; then
    run npm --prefix desktop ci
  else
    run npm --prefix desktop install
  fi
  ok "Frontend dependencies installed."
}

initialize_vault() {
  mkdir -p \
    vault/notes/system \
    vault/assets \
    vault/.anubis \
    state \
    state/obsidian_vault/hermes \
    state/obsidian_vault/memories \
    state/dev_servers

  if [[ ! -f vault/notes/welcome.md ]]; then
    cat > vault/notes/welcome.md <<'EOF'
# Welcome

Anubis Desktop OS vault initialized.
EOF
  fi

  if [[ ! -f vault/notes/system/knowledge-ingestion-policy.md ]]; then
    cat > vault/notes/system/knowledge-ingestion-policy.md <<'EOF'
# Knowledge Ingestion Policy

Markdown is the durable source of truth. Vector indexes are rebuildable.
EOF
  fi

  ok "Vault and state folders initialized."
}

start_qdrant_if_requested() {
  if [[ "$START_QDRANT" != "true" ]]; then
    warn "Qdrant startup skipped. Use --start-qdrant to start local vector services."
    return 0
  fi

  if ! need_command docker; then
    warn "Docker is not available; cannot start Qdrant."
    return 0
  fi

  if ! docker info >/dev/null 2>&1; then
    warn "Docker daemon is not reachable; cannot start Qdrant."
    return 0
  fi

  run docker compose up -d qdrant redis
  ok "Qdrant and Redis startup requested."
}

port_open() {
  local port="$1"
  python - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.4)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

initialize_rag() {
  # shellcheck disable=SC1091
  . .venv/bin/activate

  if ! port_open 6333; then
    warn "Qdrant is not reachable on 127.0.0.1:6333; RAG reindex skipped."
    return 0
  fi

  info "Initializing RAG index from Markdown vault."
  python - <<'PY'
from rag.shared.backend_legacy.indexer import RagIndexer

count = RagIndexer().reindex_all()
print(f"Indexed {count} Markdown chunks.")
PY
  ok "RAG initialization complete."
}

configure_git_identity() {
  if [[ "$CONFIGURE_GIT" != "true" ]]; then
    warn "Skipping Git identity configuration."
    return 0
  fi

  if [[ -x scripts/git-fix-identity.sh ]]; then
    run scripts/git-fix-identity.sh
  else
    run git config --local user.name "seclib"
    run git config --local user.email "thaerudit@gmail.com"
  fi
  ok "Git identity configured."
}

main() {
  info "Starting $APP_NAME setup in $ROOT_DIR"
  info "Log file: $LOG_FILE"

  install_system_dependencies
  setup_python
  setup_frontend
  initialize_vault
  start_qdrant_if_requested
  initialize_rag
  configure_git_identity

  ok "$APP_NAME setup complete."
  info "Next steps:"
  info "  make qdrant      # start vector services when needed"
  info "  make backend     # start local FastAPI"
  info "  make desktop     # start Tauri desktop UI"
}

main "$@"
