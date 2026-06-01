#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_HOST="${ANUBIS_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${ANUBIS_BACKEND_PORT:-8000}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
LOG_DIR="$ROOT_DIR/state/dev_servers"
BACKEND_LOG="$LOG_DIR/anubis-backend.log"
BACKEND_PID=""
STARTED_BACKEND="false"

if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_GREEN=$'\033[32m'
  C_BLUE=$'\033[34m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
else
  C_RESET=""
  C_GREEN=""
  C_BLUE=""
  C_YELLOW=""
  C_RED=""
fi

info() { printf '%s[Anubis]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok() { printf '%s[ OK ]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
fail() { printf '%s[FAIL]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }

info "ROOT_DIR = $ROOT_DIR"

usage() {
  cat <<EOF
Usage: ./start.sh [options]

Lance Anubis en une commande: backend + desktop.

Options:
  --backend-only     Lance seulement le backend.
  --desktop-only     Lance seulement le desktop.
  --no-backend       Alias de --desktop-only.
  -h, --help         Affiche cette aide.

Variables:
  ANUBIS_BACKEND_HOST=127.0.0.1
  ANUBIS_BACKEND_PORT=8000
EOF
}

MODE="all"
while (($#)); do
  case "$1" in
    --backend-only)
      MODE="backend"
      ;;
    --desktop-only|--no-backend)
      MODE="desktop"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Option inconnue: $1"
      usage >&2
      exit 2
      ;;
  esac
  shift
done

port_open() {
  (echo >"/dev/tcp/$BACKEND_HOST/$BACKEND_PORT") >/dev/null 2>&1
}

wait_for_backend() {
  local attempt
  for attempt in $(seq 1 60); do
    if port_open; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

cleanup() {
  if [[ "$STARTED_BACKEND" == "true" && -n "$BACKEND_PID" ]]; then
    if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      info "Arrêt du backend..."
      kill "$BACKEND_PID" >/dev/null 2>&1 || true
      wait "$BACKEND_PID" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup EXIT INT TERM

start_backend() {
  if port_open; then
    ok "Backend déjà disponible sur $BACKEND_URL"
    return 0
  fi

  mkdir -p "$LOG_DIR"
  info "Démarrage du backend sur $BACKEND_URL"
  info "Logs backend: $BACKEND_LOG"
  (
    cd "$ROOT_DIR"
    # Use absolute path to ensure script runs even if working directory changes
    exec "$ROOT_DIR/scripts/dev_backend.sh"
  ) >"$BACKEND_LOG" 2>&1 &
  BACKEND_PID="$!"
  STARTED_BACKEND="true"

  if ! wait_for_backend; then
    fail "Le backend n'a pas démarré."
    fail "Consulte les logs: $BACKEND_LOG"
    exit 1
  fi
  ok "Backend prêt"
}

start_desktop() {
  info "Lancement du desktop..."
    (
      cd "$ROOT_DIR"
      # Run the desktop launcher in the foreground (no exec) so the backend stays alive
      "$ROOT_DIR/scripts/launch_anubis_desktop.sh"
    )
}

case "$MODE" in
  all)
    start_backend
    start_desktop
    ;;
  backend)
    start_backend
    ok "Backend lancé. Appuie sur Ctrl+C pour arrêter."
    while true; do sleep 3600; done
    ;;
  desktop)
    start_desktop
    ;;
esac
