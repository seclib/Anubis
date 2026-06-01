# Launcher

The launcher owns local process orchestration for Anubis Desktop OS.

## Entry Point

- Native Tauri entrypoint: `desktop/src-tauri/src/main.rs`
- Service manager implementation: `desktop/src-tauri/src/service_manager.rs`

## Interface

The Tauri command interface is:

- `start_anubis`
- `stop_anubis`
- `restart_anubis`
- `get_anubis_status`
- `get_anubis_logs`

The service manager starts and stops:

- Qdrant and Redis through Docker Compose
- Desktop FastAPI through `backend.main:app`
- A lightweight agent orchestrator supervisor
- The current Tauri frontend process

Logs are emitted as `anubis-log` events and retained in a bounded in-memory
buffer for the dashboard.

## Watchdog

The launcher starts a self-healing watchdog from
`desktop/src-tauri/src/watchdog.rs`.

- Backend heartbeat: managed process plus local port `8000`.
- Agent heartbeat: managed supervisor process.
- Recovery: restart failed backend/agent services automatically.
- Notification: emit `anubis-watchdog` events and write watchdog log lines.

## Coupling Rule

The launcher may call external process entrypoints. It must not import Python
agent, RAG, or vault internals directly.
