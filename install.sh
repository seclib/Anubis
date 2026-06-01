#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Anubis Desktop OS"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${ANUBIS_INSTALL_LOG:-$ROOT_DIR/state/install.log}"
INSTALL_SYSTEM="${ANUBIS_INSTALL_SYSTEM:-true}"
INSTALL_FRONTEND="${ANUBIS_INSTALL_FRONTEND:-true}"
START_QDRANT="${ANUBIS_START_QDRANT:-true}"
INSTALL_DESKTOP="${ANUBIS_INSTALL_DESKTOP:-true}"
BUILD_DESKTOP="${ANUBIS_BUILD_DESKTOP:-false}"
ROLLBACK_ON_FAILURE="${ANUBIS_ROLLBACK_ON_FAILURE:-true}"

CREATED_PATHS=()
STARTED_QDRANT="false"

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
Usage: ./install.sh [options]

One-click installer for $APP_NAME.

Options:
  --no-system          Do not install missing system packages.
  --no-frontend        Do not install desktop app dependencies.
  --no-qdrant          Do not start Qdrant and Redis.
  --no-desktop         Do not install the desktop menu launcher.
  --build-desktop      Try to build the native Tauri desktop app.
  --no-rollback        Keep created files if installation fails.
  -h, --help           Show this help.

Environment:
  ANUBIS_INSTALL_LOG=state/install.log
  ANUBIS_INSTALL_SYSTEM=true|false
  ANUBIS_INSTALL_FRONTEND=true|false
  ANUBIS_START_QDRANT=true|false
  ANUBIS_INSTALL_DESKTOP=true|false
  ANUBIS_BUILD_DESKTOP=true|false
  ANUBIS_ROLLBACK_ON_FAILURE=true|false
EOF
}

while (($#)); do
  case "$1" in
    --no-system)
      INSTALL_SYSTEM="false"
      ;;
    --no-frontend)
      INSTALL_FRONTEND="false"
      ;;
    --no-qdrant)
      START_QDRANT="false"
      ;;
    --no-desktop)
      INSTALL_DESKTOP="false"
      ;;
    --build-desktop)
      BUILD_DESKTOP="true"
      ;;
    --no-rollback)
      ROLLBACK_ON_FAILURE="false"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$(dirname -- "$LOG_FILE")"
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

need_command() {
  command -v "$1" >/dev/null 2>&1
}

remember_created_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    CREATED_PATHS+=("$path")
  fi
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

rollback() {
  if [[ "$ROLLBACK_ON_FAILURE" != "true" ]]; then
    warn "Rollback disabled. Created files were left in place."
    return 0
  fi

  warn "Rolling back files created during this installer run."
  if [[ "$STARTED_QDRANT" == "true" ]] && need_command docker; then
    docker compose down >/dev/null 2>&1 || true
  fi

  local path
  for ((idx=${#CREATED_PATHS[@]}-1; idx>=0; idx--)); do
    path="${CREATED_PATHS[$idx]}"
    if [[ -e "$path" ]]; then
      rm -rf -- "$path"
      warn "Removed $path"
    fi
  done
}

on_error() {
  local code=$?
  fail "Installation failed at line $1 with exit code $code."
  fail "Log file: $LOG_FILE"
  rollback
  exit "$code"
}
trap 'on_error $LINENO' ERR

detect_linux_distribution() {
  DISTRO_ID="unknown"
  DISTRO_NAME="Unknown Linux"
  DISTRO_LIKE=""
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_NAME="${PRETTY_NAME:-${NAME:-Unknown Linux}}"
    DISTRO_LIKE="${ID_LIKE:-}"
  fi

  case "$DISTRO_ID $DISTRO_LIKE" in
    *debian*|*ubuntu*|*kali*)
      PACKAGE_MANAGER="apt"
      ;;
    *)
      if need_command apt-get; then
        PACKAGE_MANAGER="apt"
      else
        PACKAGE_MANAGER=""
      fi
      ;;
  esac

  info "Detected distribution: $DISTRO_NAME"
  if [[ -n "$PACKAGE_MANAGER" ]]; then
    ok "Package manager: $PACKAGE_MANAGER"
  else
    warn "No supported package manager detected. Debian, Ubuntu, and Kali are supported automatically."
  fi
}

apt_package_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"
}

install_missing_apt_packages() {
  local requested=("$@")
  local missing=()
  local package

  for package in "${requested[@]}"; do
    if ! apt_package_installed "$package"; then
      missing+=("$package")
    fi
  done

  if ((${#missing[@]} == 0)); then
    ok "System packages are already installed."
    return 0
  fi

  info "Installing missing packages: ${missing[*]}"
  run sudo_cmd apt-get update
  run sudo_cmd apt-get install -y "${missing[@]}"
}

install_system_dependencies() {
  if [[ "$INSTALL_SYSTEM" != "true" ]]; then
    warn "Skipping system package installation."
    return 0
  fi

  if [[ "$PACKAGE_MANAGER" != "apt" ]]; then
    warn "Automatic system package installation is only configured for Debian, Ubuntu, and Kali."
    return 0
  fi

  local packages=(
    ca-certificates
    curl
    git
    python3
    python3-venv
    python3-pip
    nodejs
    npm
    docker.io
    docker-compose-plugin
    desktop-file-utils
    xdg-utils
    build-essential
    pkg-config
    libssl-dev
    cargo
    libwebkit2gtk-4.1-dev
    libjavascriptcoregtk-4.1-dev
    libsoup-3.0-dev
    libgtk-3-dev
    libayatana-appindicator3-dev
    librsvg2-dev
  )

  install_missing_apt_packages "${packages[@]}"
}

create_python_environment() {
  cd "$ROOT_DIR"
  if ! need_command python3; then
    fail "Python 3 is required. Please install Python 3 and run the installer again."
    exit 1
  fi

  remember_created_path "$ROOT_DIR/.venv"
  if [[ ! -d "$ROOT_DIR/.venv" ]]; then
    run python3 -m venv "$ROOT_DIR/.venv"
  else
    ok "Python environment already exists."
  fi

  run "$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
  run "$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt"
  if [[ -f "$ROOT_DIR/backend/requirements.txt" ]]; then
    run "$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
  fi
  install_nested_python_packages
  ok "Python environment is ready."
}

install_nested_python_packages() {
  local packages=(
    "$ROOT_DIR/anubis/kernel"
    "$ROOT_DIR/anubis/packages/prompt-engine"
    "$ROOT_DIR/anubis/packages/memory-sdk"
    "$ROOT_DIR/anubis/services/tools"
    "$ROOT_DIR/anubis/services/rag"
    "$ROOT_DIR/anubis/services/ai-core"
  )
  local package

  for package in "${packages[@]}"; do
    if [[ -f "$package/pyproject.toml" ]]; then
      run "$ROOT_DIR/.venv/bin/python" -m pip install -e "$package"
    fi
  done
  ok "Nested Anubis Python packages are installed."
}

install_frontend_dependencies() {
  if [[ "$INSTALL_FRONTEND" != "true" ]]; then
    warn "Skipping frontend dependency installation."
    return 0
  fi

  if ! need_command npm; then
    fail "npm is required for the desktop app. Install Node.js/npm or rerun with --no-frontend."
    exit 1
  fi

  if ! need_command node; then
    fail "Node.js is required for the desktop app. Install Node.js 20+ or rerun with --no-frontend."
    exit 1
  fi

  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || printf '0')"
  if ((node_major < 20)); then
    fail "Node.js 20 or newer is required for Vite/Tauri. Found: $(node --version)"
    exit 1
  fi

  remember_created_path "$ROOT_DIR/desktop/node_modules"
  if [[ -f "$ROOT_DIR/desktop/package-lock.json" ]]; then
    run npm --prefix "$ROOT_DIR/desktop" ci
  else
    run npm --prefix "$ROOT_DIR/desktop" install
  fi
  ok "Desktop app dependencies are ready."
}

configure_qdrant() {
  mkdir -p "$ROOT_DIR/state"

  if [[ "$START_QDRANT" != "true" ]]; then
    warn "Skipping Qdrant startup."
    return 0
  fi

  if ! need_command docker; then
    warn "Docker is not installed, so Qdrant cannot be started automatically."
    return 0
  fi

  if ! docker info >/dev/null 2>&1; then
    warn "Docker is installed but not reachable. Start Docker, then run: docker compose up -d qdrant redis"
    return 0
  fi

  run docker compose up -d qdrant redis
  STARTED_QDRANT="true"
  ok "Qdrant and Redis are configured."
}

configure_environment_file() {
  local env_file="$ROOT_DIR/.env"
  remember_created_path "$env_file"

  touch "$env_file"
  if ! grep -q '^ANUBIS_VAULT_PATH=' "$env_file"; then
    printf 'ANUBIS_VAULT_PATH=vault\n' >> "$env_file"
  fi
  if ! grep -q '^QDRANT_URL=' "$env_file"; then
    printf 'QDRANT_URL=http://localhost:6333\n' >> "$env_file"
  fi
  if ! grep -q '^QDRANT_COLLECTION=' "$env_file"; then
    printf 'QDRANT_COLLECTION=anubis_chunks\n' >> "$env_file"
  fi
  ok "Local configuration file is ready."
}

initialize_vault() {
  remember_created_path "$ROOT_DIR/vault"
  remember_created_path "$ROOT_DIR/state"
  mkdir -p \
    "$ROOT_DIR/vault/notes/system" \
    "$ROOT_DIR/vault/assets" \
    "$ROOT_DIR/vault/.anubis" \
    "$ROOT_DIR/state" \
    "$ROOT_DIR/state/obsidian_vault/hermes" \
    "$ROOT_DIR/state/obsidian_vault/memories" \
    "$ROOT_DIR/state/dev_servers"

  if [[ ! -f "$ROOT_DIR/vault/notes/welcome.md" ]]; then
    cat > "$ROOT_DIR/vault/notes/welcome.md" <<'EOF'
# Welcome

Anubis Desktop OS is ready.

Use this vault for notes, memory, plans, and useful knowledge.
EOF
  fi

  if [[ ! -f "$ROOT_DIR/vault/notes/system/knowledge-ingestion-policy.md" ]]; then
    cat > "$ROOT_DIR/vault/notes/system/knowledge-ingestion-policy.md" <<'EOF'
# Knowledge Ingestion Policy

Markdown notes are the durable source of truth. Search indexes can be rebuilt from the vault.
EOF
  fi

  ok "Vault and state folders are ready."
}

install_desktop_launcher() {
  if [[ "$INSTALL_DESKTOP" != "true" ]]; then
    warn "Skipping desktop launcher installation."
    return 0
  fi

  if [[ ! -x "$ROOT_DIR/scripts/install_desktop_entry.sh" ]]; then
    chmod 0755 "$ROOT_DIR/scripts/install_desktop_entry.sh"
  fi

  remember_created_path "${XDG_DATA_HOME:-$HOME/.local/share}/applications/Anubis.desktop"
  remember_created_path "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/anubis.svg"
  run "$ROOT_DIR/scripts/install_desktop_entry.sh"
  ok "Desktop launcher installed."
}

build_desktop_if_requested() {
  if [[ "$BUILD_DESKTOP" != "true" ]]; then
    warn "Native desktop build skipped. Use --build-desktop to build it during install."
    return 0
  fi

  if ! need_command cargo; then
    fail "cargo is required to build the native desktop app."
    exit 1
  fi

  if ! need_command npm; then
    fail "npm is required to build the native desktop app."
    exit 1
  fi

  run npm --prefix "$ROOT_DIR/desktop" run tauri -- build
  ok "Native desktop app built."
}

port_open() {
  local port="$1"
  "$ROOT_DIR/.venv/bin/python" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.5)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

verify_installation() {
  info "Verifying installation."

  [[ -x "$ROOT_DIR/.venv/bin/python" ]]
  ok "Python environment found."

  "$ROOT_DIR/.venv/bin/python" - <<'PY'
import importlib

for module in ("backend.main", "backend.api.routes.health", "agent.multi_agent"):
    importlib.import_module(module)
print("Python imports are healthy.")
PY
  ok "Python imports verified."

  if [[ "$INSTALL_FRONTEND" == "true" ]]; then
    [[ -d "$ROOT_DIR/desktop/node_modules" ]]
    ok "Desktop dependencies found."
    run npm --prefix "$ROOT_DIR/desktop" run build
    ok "Desktop frontend build verified."
  fi

  [[ -f "$ROOT_DIR/vault/notes/welcome.md" ]]
  ok "Vault initialized."

  if [[ "$START_QDRANT" == "true" ]]; then
    if port_open 6333; then
      ok "Qdrant is reachable on port 6333."
    else
      warn "Qdrant is not reachable yet. Docker may still be starting, or Docker may need to be started manually."
    fi
  fi

  if [[ "$INSTALL_DESKTOP" == "true" ]]; then
    [[ -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/Anubis.desktop" ]]
    ok "Desktop launcher entry found."
  fi
}

print_success() {
  ok "$APP_NAME installation complete."
  info "Open Anubis from your application menu, or run:"
  info "  scripts/launch_anubis_desktop.sh"
  info "Installer log:"
  info "  $LOG_FILE"
}

main() {
  cd "$ROOT_DIR"
  info "Installing $APP_NAME"
  info "Install folder: $ROOT_DIR"
  info "Log file: $LOG_FILE"

  detect_linux_distribution
  install_system_dependencies
  create_python_environment
  install_frontend_dependencies
  configure_environment_file
  configure_qdrant
  initialize_vault
  install_desktop_launcher
  build_desktop_if_requested
  verify_installation
  print_success
}

main "$@"
