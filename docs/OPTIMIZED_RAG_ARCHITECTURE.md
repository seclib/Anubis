# Optimized RAG Architecture

ANUBIS RAG now uses `retrieval.optimized.OptimizedRetriever` as the default retrieval path.

## Pipeline

1. Query routing
   - Detects semantic, truth, procedural, and hybrid intent.
   - Routes only to required channels.

2. Top-k optimization
   - Uses per-channel candidate budgets instead of flat `top_k * 8` fanout.
   - Caps final results to a small production-safe limit.

3. Hierarchical retrieval
   - Fuses candidates from Qdrant, local vectors, and keyword/Obsidian.
   - Groups results by parent/document/source.
   - Keeps only the strongest chunks per group.

4. Chunk deduplication
   - Collapses duplicate chunks by stable chunk ids when available.
   - Falls back to source plus normalized text hashes.

5. Embedding cache
   - Reuses `EmbeddingPipeline` and `CacheManager`.
   - Query embeddings are computed once and shared across channels.

6. Compact context
   - Renders final context from deduplicated hierarchical results.
   - Uses a 4000 character context budget for retrieval-only responses.

## Target Metrics

- Latency: 50% reduction through routed channel fanout and lower candidate counts.
- Tokens: 50% reduction through deduplication, group caps, and compact context rendering.

## Rollback

The previous `HybridRetriever` remains available. `RetrievalService` can be constructed with `hybrid=HybridRetriever(...)` if a deployment needs to compare behavior or roll back.
