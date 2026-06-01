# Anubis Desktop OS Repository

```text
.
├── desktop/              # Tauri desktop shell and React UI
├── backend/              # Local FastAPI API
│   ├── api/              # HTTP routes
│   ├── agent/            # Tool-calling agent and Markdown memory
│   ├── core/             # Config and path safety helpers
│   ├── rag/              # Chunking, embeddings, Qdrant indexing/retrieval
│   ├── vault/            # Markdown vault service and parser helpers
│   └── watcher/          # Filesystem watcher for Markdown changes
├── vault/                # Obsidian-like Markdown source of truth
│   ├── notes/
│   ├── assets/
│   └── .anubis/
├── scripts/              # Linux-friendly dev entrypoints
└── docker-compose.yml    # Local Qdrant and existing services
```

## Module Responsibilities

- `desktop`: note navigation, Markdown editing surface, agent chat, chunk display.
- `backend/api`: small local HTTP boundary for the desktop app.
- `backend/vault`: only layer allowed to read and write Markdown files.
- `backend/rag`: turns Markdown into chunks, embeddings and Qdrant points.
- `backend/agent`: uses tools to search RAG, read notes and inject memory.
- `backend/watcher`: observes Markdown changes and refreshes the vector index.
- `vault`: durable human-readable memory. Qdrant is rebuildable from here.

## Local Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
docker compose up -d qdrant
./scripts/dev_backend.sh
```

In another terminal:

```bash
cd desktop
npm install
npm run tauri dev
```
