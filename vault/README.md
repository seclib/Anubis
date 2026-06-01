# Vault

The vault is the human-readable Markdown source of truth for Anubis Desktop OS.

## Entry Point

- Service API: `backend.vault.service.VaultService`
- Filesystem root: `vault/`

## Interface

- List Markdown notes.
- Read Markdown notes.
- Write Markdown notes.

All paths are checked with `backend.core.paths.ensure_inside` before file I/O.

## Coupling Rule

The vault stores durable Markdown only. It does not know about Qdrant, agents,
or frontend state.
