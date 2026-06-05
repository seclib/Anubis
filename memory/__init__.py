"""Unified memory service compatibility exports.

Keep package import side-effect free so legacy modules such as ``memory.hermes``
can be imported without loading unfinished ``anubis.*`` compatibility paths.
"""

_EXPORTS = {
    "InMemoryMemoryStore": ("memory.store", "InMemoryMemoryStore"),
    "MemoryCollection": ("memory.schema", "MemoryCollection"),
    "MemoryEmbedder": ("memory.store", "MemoryEmbedder"),
    "MemoryMigrationStrategy": ("memory.migration", "MemoryMigrationStrategy"),
    "MemoryRecord": ("memory.schema", "MemoryRecord"),
    "MemorySearchQuery": ("memory.schema", "MemorySearchQuery"),
    "MemorySearchResult": ("memory.schema", "MemorySearchResult"),
    "MemoryVectorStore": ("memory.store", "MemoryVectorStore"),
    "MemoryWriteResult": ("memory.schema", "MemoryWriteResult"),
    "MigrationPlan": ("memory.schema", "MigrationPlan"),
    "QdrantMemoryStore": ("memory.store", "QdrantMemoryStore"),
    "UnifiedMemoryService": ("memory.service", "UnifiedMemoryService"),
    "build_memory_record": ("memory.migration", "build_memory_record"),
    "memory_hash": ("memory.service", "memory_hash"),
    "normalize_collection": ("memory.service", "normalize_collection"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = __import__(module_name, fromlist=[attribute])
    value = getattr(module, attribute)
    globals()[name] = value
    return value

__all__ = [
    "InMemoryMemoryStore",
    "MemoryCollection",
    "MemoryEmbedder",
    "MemoryMigrationStrategy",
    "MemoryRecord",
    "MemorySearchQuery",
    "MemorySearchResult",
    "MemoryVectorStore",
    "MemoryWriteResult",
    "MigrationPlan",
    "QdrantMemoryStore",
    "UnifiedMemoryService",
    "build_memory_record",
    "memory_hash",
    "normalize_collection",
]
