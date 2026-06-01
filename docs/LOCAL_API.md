# Anubis Desktop OS Local API

Base URL:

```text
http://127.0.0.1:8000
```

The API is local-only. Requests from non-local clients are rejected.

## Endpoints

```text
GET  /files
POST /read
POST /write
POST /update
POST /search_rag
POST /embed
POST /agent_query
GET  /health
GET  /health/ready
```

## Requests

```json
POST /read
{ "file": "notes/welcome.md" }
```

```json
POST /write
{
  "file": "notes/example.md",
  "content": "# Example\n\nReusable knowledge.",
  "index": true
}
```

```json
POST /update
{
  "file": "notes/example.md",
  "patch": "## New Section\n\nAdditional durable knowledge.",
  "index": true
}
```

```json
POST /search_rag
{ "query": "How is knowledge stored?", "limit": 6 }
```

```json
POST /embed
{ "text": "Text to embed" }
```

```json
POST /agent_query
{ "query": "How should Anubis store new knowledge?" }
```

## Flow

```text
UI opens vault
  -> GET /files

UI opens note
  -> POST /read
  -> VaultService reads Markdown

UI writes note
  -> POST /write or /update
  -> VaultService writes Markdown
  -> RagIndexer chunks Markdown
  -> LocalEmbedder creates vectors
  -> QdrantStore upserts points

UI asks question
  -> POST /agent_query
  -> AgentLoop runs rag_query first
  -> Qdrant returns chunks
  -> API returns answer + chunks_used
```
