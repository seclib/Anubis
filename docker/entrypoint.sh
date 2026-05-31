#!/bin/sh
set -eu

echo "[anubis] initializing workspace..."

APP_HOME="${APP_HOME:-/opt/anubis-agent}"
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
INIT_WORKSPACE_GIT="${INIT_WORKSPACE_GIT:-true}"
HERMES_MEMORY_BACKEND="${HERMES_MEMORY_BACKEND:-local}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_FALLBACK_URL="${QDRANT_FALLBACK_URL:-}"
QDRANT_RETRY_ATTEMPTS="${QDRANT_RETRY_ATTEMPTS:-20}"
QDRANT_RETRY_DELAY="${QDRANT_RETRY_DELAY:-2}"

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

if [ "$HERMES_MEMORY_BACKEND" = "qdrant" ]; then
  echo "[anubis-entrypoint] Checking external Qdrant at ${QDRANT_URL}/collections"

  QDRANT_SELECTED_URL="$(
    python - "$QDRANT_URL" "$QDRANT_FALLBACK_URL" "$QDRANT_RETRY_ATTEMPTS" "$QDRANT_RETRY_DELAY" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

raw_candidates = [sys.argv[1], sys.argv[2]]
candidates = []
for value in raw_candidates:
    base_url = value.rstrip("/")
    if base_url and base_url not in candidates:
        candidates.append(base_url)

attempts = max(1, int(sys.argv[3]))
delay = max(0.1, float(sys.argv[4]))
last_error = "no Qdrant URL candidate configured"

for attempt in range(1, attempts + 1):
    for base_url in candidates:
        url = f"{base_url}/collections"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and "result" in payload:
                    count = len(payload.get("result", {}).get("collections", []))
                    print(
                        f"[anubis-entrypoint] External Qdrant is reachable at {base_url}; "
                        f"{count} collection(s) visible.",
                        file=sys.stderr,
                    )
                    print(base_url)
                    raise SystemExit(0)
                last_error = f"unexpected response status={response.status} payload={payload!r}"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)

        print(
            f"[anubis-entrypoint] Qdrant connection attempt {attempt}/{attempts} "
            f"failed for {url}: {last_error}",
            file=sys.stderr,
        )

    if attempt < attempts:
        time.sleep(delay)

print(
    "[anubis-entrypoint] ERROR: Cannot connect to external Qdrant. "
    "Start the standalone ~/qdrant project or set QDRANT_URL to a reachable host.",
    file=sys.stderr,
)
raise SystemExit(1)
PY
  )"
  QDRANT_URL="$QDRANT_SELECTED_URL"
  export QDRANT_URL
fi

echo "[anubis] starting API..."

exec "$@"
