# API

## AI Core

- `GET /health`
- `POST /v1/chat`
- `GET /v1/tools`

## RAG

- `GET /health`
- `POST /ingest`
- `POST /search`
- `POST /query`

Every response includes or propagates `x-request-id`. Errors are returned as structured JSON with a stable `error.code`.
