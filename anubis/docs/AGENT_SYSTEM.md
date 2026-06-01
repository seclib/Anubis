# Agent System Integration

## Run Agent Loop

```http
POST /v1/agent/run
x-request-id: 7fbd8c3f-4f82-4d89-8e3f-1a2d61cbb1e9
content-type: application/json

{
  "conversation_id": null,
  "input": "What did we decide about local-first memory?",
  "max_steps": 12,
  "retrieve_initial_memory": true
}
```

## Response Shape

```json
{
  "conversation_id": "uuid",
  "final_output": "Agent loop completed...",
  "state": {
    "conversation_id": "uuid",
    "messages": [],
    "memory_context": [],
    "tool_results": [],
    "step_counter": 2,
    "termination_flag": true
  },
  "steps": [],
  "trace": [],
  "request_id": "7fbd8c3f-4f82-4d89-8e3f-1a2d61cbb1e9"
}
```

## Tool Boundary

The loop can only call these tool names:

- `web_search`
- `rag_query`
- `file_read`
- `file_write`
- `memory_store`
- `memory_retrieve`

Every tool result is normalized into:

```json
{
  "tool_name": "memory_retrieve",
  "status": "succeeded",
  "output": {},
  "error": null
}
```
