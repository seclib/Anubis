# Backend

The backend is the canonical Desktop OS HTTP API.

## Entry Point

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Interfaces

- `GET /health`
- `GET /health/ready`
- `GET /files`
- `POST /read`
- `POST /write`
- `POST /update`
- `POST /search_rag`
- `POST /embed`
- `POST /agent_query`
- `GET/PUT /notes`
- `POST /rag/search`
- `POST /rag/reindex`
- `POST /agent/chat`

## Coupling Rule

Routes may depend on backend services through small lazy factories. They should
not construct global Qdrant, vault, or agent objects at import time.
