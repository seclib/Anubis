# Anubis Desktop Launcher

The Tauri desktop app is the local-first launcher for Anubis Desktop OS.

## Services

- `RAG / Qdrant`: starts `docker compose up --no-color qdrant redis`.
- `Backend API`: starts `.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` when the virtualenv exists, otherwise falls back to `python3`.
- `Agent Orchestrator`: starts a lightweight local supervisor that validates the Anubis multi-agent roster and stays alive while the system is running.
- `Memory System`: reports local Hermes/query-cache file availability.
- `Desktop Frontend`: the current Tauri UI process.

The process manager lives in `desktop/src-tauri/src/service_manager.rs`.
The self-healing watchdog lives in `desktop/src-tauri/src/watchdog.rs`.

## Startup Flow

1. The UI calls the Tauri command `start_anubis`.
2. The main process starts RAG/cache first, then the FastAPI backend, then the agent swarm supervisor.
3. Each child process has stdout/stderr captured by the Rust service manager.
4. Log lines are stored in a bounded in-memory buffer and emitted to the UI through the `anubis-log` event.
5. The status panel polls `get_anubis_status`, combining child-process state with local port checks for backend `8000`, Qdrant `6333`, and Redis `6379`.

## Self-Healing Watchdog

- The watchdog starts with the launcher process.
- It checks backend and agent heartbeats every three seconds.
- Backend is considered unhealthy when its managed process exits or its `8000`
  heartbeat stays closed after the startup grace period.
- Agent orchestrator is considered unhealthy when its supervisor process exits.
- Failures are logged with the reason, restart count, and service name.
- Restart notifications are emitted to the UI through `anubis-watchdog`.
- The dashboard shows restart count, last failure, heartbeat age, and a live
  watchdog alert.

## Stop / Restart

- `stop_anubis` stops agent, backend, then RAG/cache.
- Managed processes receive a graceful `TERM` signal first; if they do not exit within five seconds the launcher forces shutdown.
- RAG stop also runs `docker compose stop qdrant redis` so local containers are left clean.
- `restart_anubis` runs the stop flow followed by the start flow.

## Linux Dependencies

Tauri on Linux requires WebKitGTK system packages. On Kali/Debian-like systems install the distro equivalents for:

```bash
sudo apt install libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev
```

Node/npm are required for the Vite frontend build.
