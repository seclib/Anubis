# Communication Examples

## Desktop to AI Core

The Tauri command `send_chat_message` posts to AI Core:

```http
POST http://127.0.0.1:8100/v1/chat
x-request-id: <uuid>
content-type: application/json

{
  "conversation_id": null,
  "message": "Summarize my project memory"
}
```

## AI Core to RAG

AI Core retrieves context before prompting the LLM:

```http
POST http://127.0.0.1:8101/search
x-request-id: <same request id>
content-type: application/json

{
  "query": "Summarize my project memory",
  "limit": 5
}
```

## Ingesting Memory

```http
POST http://127.0.0.1:8101/ingest
content-type: application/json

{
  "documents": [
    {
      "title": "Architecture Decision",
      "content": "# Decision\nUse local-first storage and Qdrant-backed memory.",
      "source_type": "markdown",
      "metadata": {
        "workspace": "default"
      }
    }
  ]
}
```

## Tool Registry

AI Core lists available tools through the registry:

```http
GET http://127.0.0.1:8100/v1/tools
```
