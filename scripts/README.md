# Scripts

Repository automation lives here.

## Entry Points

- `setup.sh`: idempotent installer for local development.
- `check.sh`: local verification baseline.
- `dev_backend.sh`: starts the Desktop OS backend.
- `watch_vault.sh`: watches Markdown vault changes.
- `git-fix-identity.sh`: enforces Git author identity and hooks.
- `git-audit-authors.sh`: audits commit author metadata.

## Coupling Rule

Scripts may orchestrate services and call public entrypoints. They should avoid
embedding business logic that belongs in backend, RAG, agent, or launcher code.
