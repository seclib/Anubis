folder structure

```text
backend/
  agent/
    llm.py
    loop.py
    memory.py
    multi_agent.py
    prompts.py
    tools.py
  rag/
    chunker.py
    embedder.py
    indexer.py
    qdrant_store.py
    retriever.py
  skills/
    engine.py
    parser.py
  tools/
    sandbox.py
  vault/
    markdown.py
    service.py
scripts/
  ingest_obsidian.py
  run_agent.py
  run_multi_agent.py
  watch_obsidian.py
vault/
  skills/
    docker_debug.md
```

run

```bash
docker compose up -d qdrant
python3 scripts/ingest_obsidian.py
python3 scripts/run_agent.py "debug docker container startup failure"
python3 scripts/run_multi_agent.py "inspect project tests"
python3 scripts/watch_obsidian.py
```
