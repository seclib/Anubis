# Anubis Desktop Launcher

The Tauri desktop app is the local-first launcher for Anubis Desktop OS.

## Services

- `RAG / Qdrant`: starts `docker compose up --no-color qdrant redis`.
- `Backend API`: starts `python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.
- `Agent Swarm`: starts a lightweight local supervisor that validates the Anubis multi-agent roster and stays alive while the system is running.
- `Memory System`: reports local Hermes/query-cache file availability.
- `Desktop Frontend`: the current Tauri UI process.

## Startup Flow

1. The UI calls the Tauri command `start_anubis`.
2. The main process starts RAG/cache first, then the FastAPI backend, then the agent swarm supervisor.
3. Each child process has stdout/stderr captured by the Rust service manager.
4. Log lines are stored in a bounded in-memory buffer and emitted to the UI through the `anubis-log` event.
5. The status panel polls `get_anubis_status`, combining child-process state with local port checks for backend `8000` and Qdrant `6333`.

## Stop / Restart

- `stop_anubis` stops agent, backend, then RAG/cache.
- RAG stop also runs `docker compose stop qdrant redis` so local containers are left clean.
- `restart_anubis` runs the stop flow followed by the start flow.

## Linux Dependencies

Tauri on Linux requires WebKitGTK system packages. On Kali/Debian-like systems install the distro equivalents for:

```bash
sudo apt install libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev libsoup-3.0-dev
```

Node/npm are required for the Vite frontend build.
