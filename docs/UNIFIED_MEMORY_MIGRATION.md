# Unified Memory Migration

ANUBIS memory is consolidated behind `anubis.memory.UnifiedMemoryService`.
The service writes all durable memory to Qdrant collections:

- `repo`: repository chunks, code facts, structural metadata
- `docs`: Obsidian and markdown knowledge
- `conversations`: task history, agent messages, decision records

## Strategy

1. Snapshot legacy memory files and existing vector stores.
2. Start Qdrant and create collections lazily through `UnifiedMemoryService`.
3. Migrate repository memory with `MemoryMigrationStrategy.migrate_repo_memory`.
4. Migrate Obsidian notes with `MemoryMigrationStrategy.migrate_obsidian_notes`.
5. Migrate conversation history with `MemoryMigrationStrategy.migrate_conversation_memory`.
6. Run parity retrieval checks against legacy memory paths.
7. Move callers to `UnifiedMemoryService.retrieve`.
8. Keep legacy stores read-only until retrieval parity is accepted.

## Safety Rules

- Migration is append-only.
- Legacy files are never deleted by the migration layer.
- Content hashes deduplicate records per collection.
- Collections load only when queried or written.
- Rollback is caller-level: point retrieval back to legacy memory while Qdrant data remains isolated.

## Production Store

Use `QdrantMemoryStore` for deployment:

```python
from anubis.memory import QdrantMemoryStore, UnifiedMemoryService

service = UnifiedMemoryService(store=QdrantMemoryStore(url="http://qdrant:6333"))
```

Tests and single-node development can use the default in-memory store.
