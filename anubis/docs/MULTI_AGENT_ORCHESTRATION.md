# Multi-Agent Orchestration

## System Architecture

```text
User Input
  |
  v
AI Core /v1/orchestrator/run
  |
  v
Session Manager
  |
  v
Planner Agent
  |
  v
Execution Plan JSON DAG
  |
  v
Executor Agent
  |
  v
Tool Runtime Sandbox
  |
  v
RAG / Memory Retrieval if needed
  |
  v
Critic Agent
  |
  +--> approved -> Final Response
  |
  +--> rejected -> loop back to Executor with fix_instructions
  |
  v
Memory Write Decision optional, never automatic
```

## Codebase Structure

```text
services/ai-core/src/anubis_ai_core/
  models/
    orchestration.py
  orchestrator/
    json_agent.py
    planner_agent.py
    executor_agent.py
    critic_agent.py
    engine.py
    memory_write_policy.py
    session_manager.py
    trace_logger.py
  api/
    dependencies.py
    routes.py
```

## API

```http
POST /v1/orchestrator/run
content-type: application/json

{
  "conversation_id": null,
  "input": "What did we decide about local-first memory?",
  "max_iterations": 3
}
```

## Final Loop

```text
User Input
   -> Session Manager
   -> Planner Agent
   -> Execution Plan JSON DAG
   -> Executor Agent
   -> Tool Runtime Sandbox
   -> RAG / Memory retrieval if needed
   -> Critic Agent
   -> approve OR loop back Executor
   -> Final Response
   -> Memory Write Decision optional
```

## Replay Support

`OrchestratorRunRequest.replay_trace` accepts prior trace events. The orchestrator includes them in the returned trace so UI/debug tooling can compare old and new stage outputs.
