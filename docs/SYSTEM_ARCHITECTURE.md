# Anubis Desktop OS Architecture

This document defines the production-facing module boundaries. Existing legacy
packages remain available for compatibility, but new Desktop OS work should use
the boundaries below.

## Folder Structure

```text
launcher/   Launcher contract, service manifest, and process ownership docs.
backend/    Canonical local FastAPI API for the desktop app.
agent/      Autonomous and multi-agent cognition modules.
rag/        RAG facades and retrieval contracts.
vault/      Markdown source of truth.
frontend/   Frontend contract for the Tauri/React UI in desktop/.
scripts/    Setup, checks, Git hygiene, and local automation.
```

Implementation locations that are intentionally kept for compatibility:

```text
desktop/          Tauri and React implementation for frontend + native shell.
backend/rag/      Desktop-specific RAG implementation.
backend/vault/    Desktop-specific vault service.
runtime/          Composition root for the legacy autonomous agent runtime.
app/              Legacy OpenAI-compatible API.
retrieval/        Legacy hybrid retrieval engine used by rag.service.
```

## Runtime Flow

```text
frontend
  -> launcher commands for service lifecycle/logs
  -> backend HTTP API for notes, RAG, and agent chat

backend
  -> backend.agent for Desktop chat adapter
  -> backend.rag for chunk/index/search
  -> backend.vault for safe Markdown I/O

agent runtime
  -> runtime dependency injection
  -> executor/tools
  -> memory/retrieval as injected services
```

## Entry Points

- Launcher: `desktop/src-tauri/src/main.rs`
- Launcher service manager: `desktop/src-tauri/src/service_manager.rs`
- Backend: `backend.main:app`
- Frontend: `desktop/src/main.tsx`
- Desktop RAG: `backend.rag.indexer.RagIndexer`, `backend.rag.retriever.RagRetriever`
- Vault: `backend.vault.service.VaultService`
- Autonomous agent: `runtime.agent_runner.run_agent_loop`
- Desktop chat adapter: `backend.agent.loop.AgentLoop`

## Coupling Rules

- Launcher starts processes and reads health, but does not import Python internals.
- Frontend talks through Tauri commands and HTTP only.
- Backend routes use lazy factories; no heavy service construction at import time.
- RAG can depend on vault and vector storage; it cannot depend on frontend or launcher.
- Vault owns Markdown I/O only.
- Agent code receives tools and memory through runtime boundaries.
- Scripts orchestrate public entrypoints and do not contain domain logic.

## Logging

- Backend HTTP requests log through `anubis.api`.
- Desktop agent routes log through `anubis.api.agent`.
- Vault operations log through `anubis.vault`.
- RAG indexing/search/Qdrant operations log through `anubis.rag.*`.
- Launcher process output is captured by the Tauri service manager and emitted as
  live `anubis-log` events.

## Compatibility Notes

The repo still contains older `app/`, root `main.py`, root `rag/`, `retrieval/`,
and runtime modules. They are kept because current CLI/API behavior depends on
them. Prefer additive adapters over large moves until those entrypoints have
dedicated migration tests.
