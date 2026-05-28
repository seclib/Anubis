#!/bin/sh
set -eu

echo "[anubis] initializing workspace..."

APP_HOME="${APP_HOME:-/opt/anubis-agent}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
INIT_WORKSPACE_GIT="${INIT_WORKSPACE_GIT:-true}"

mkdir -p "$WORKSPACE_DIR/state"

if [ -z "$(find "$WORKSPACE_DIR" -mindepth 1 -maxdepth 1 ! -name state -print -quit)" ]; then
  echo "[anubis-entrypoint] Seeding isolated workspace from $APP_HOME"

  tar \
    --exclude='./state' \
    --exclude='./__pycache__' \
    --exclude='./*/__pycache__' \
    --exclude='./.git' \
    -C "$APP_HOME" -cf - . | tar -C "$WORKSPACE_DIR" -xf -
fi

if [ "$INIT_WORKSPACE_GIT" = "true" ] && [ ! -d "$WORKSPACE_DIR/.git" ] && command -v git >/dev/null 2>&1; then
  echo "[anubis-entrypoint] Initializing isolated workspace Git repository"

  git -C "$WORKSPACE_DIR" init >/dev/null 2>&1 || true
  git -C "$WORKSPACE_DIR" config user.email "anubis@example.local" >/dev/null 2>&1 || true
  git -C "$WORKSPACE_DIR" config user.name "Anubis Agent" >/dev/null 2>&1 || true
  git -C "$WORKSPACE_DIR" add -A >/dev/null 2>&1 || true
  git -C "$WORKSPACE_DIR" commit -m "Initial isolated workspace snapshot" >/dev/null 2>&1 || true
fi

echo "[anubis] starting API..."

exec "$@"