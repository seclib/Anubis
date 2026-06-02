# ANUBIS Desktop MVP

ANUBIS is a local-first AI runtime, not a standalone dashboard app. The MVP keeps
the user in one focused vertical workspace while delegating all agent, RAG,
memory, tool, and plugin behavior to local runtime modules.

## Architecture

```text
desktop-ui/          React focus shell, command palette, API client
runtime-tauri/       Rust desktop bridge, native menus, local commands
core/                Agent/runtime contracts and workspace primitives
runtime/             Agent loop, streaming, tools, plugin primitives
backend/             FastAPI local API, vault/RAG/skills services
plugins/             Local extension manifests
skills/              Skill/plugin packs and Markdown procedures
vault/               Local knowledge base
```

## Runtime Boundaries

- React never imports Python or reads project files directly.
- Tauri owns desktop concerns: native menu, local command invocation, plugin
  manifest discovery, and backend health checks.
- FastAPI remains the local agent API. The shell sends chat work to `/ask`.
- Plugin manifests are local data. Agent-side execution stays behind runtime
  services and explicit permissions.

## MVP Features

- Single-column centered focus window.
- Agent chat as the primary interface.
- Ctrl+K command palette with runtime and plugin commands.
- Desktop menu model: File, Tools, Project, View.
- Minimal local plugin manifest system.
- Browser dev fallback against `http://127.0.0.1:8000`.

## Implementation Plan

1. Stabilize local backend startup behind one command.
2. Add streaming chat once the agent loop exposes a stable event contract.
3. Connect menu events to frontend actions through Tauri event listeners.
4. Extend plugin manifests with command contributions and permissions.
5. Add vault open/sync commands in Tauri with explicit path controls.
6. Add focused tests for plugin discovery and frontend API normalization.

## Run

```bash
cd desktop-ui
npm install
npm run build
npm run tauri dev
```

The desktop shell expects the local API at `http://127.0.0.1:8000` unless
`ANUBIS_API_URL` is set.
