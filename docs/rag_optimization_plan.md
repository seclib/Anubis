# ANUBIS RAG Optimization Plan

Date: 2026-06-05

## Goal

Optimize ANUBIS RAG architecture to reduce:

- latency
- memory consumption
- token usage

This is a design-only plan. No implementation is included.

## Current State

Current RAG/retrieval systems:

- `core/memory/vector_store.py`
- `core/memory/retriever.py`
- `core/memory/memory_manager.py`
- `core/memory/semantic_vector_store.py`
- `src/anubis/memory.py`
- `src/anubis/retrieval.py`

Current behavior:

- deterministic local hashing embeddings
- in-memory vector stores
- linear scan retrieval
- duplicated embedding classes
- duplicated retrieval query/response classes
- no external vector database
- no chunk deduplication ledger
- no shared embedding cache

Measured baseline:

| Metric | Current |
| --- | ---: |
| Core indexing median | `0.025 ms` per record |
| Scoped RAG indexing median | `0.034 ms` per record |
| Core retrieval over 1,000 records median | `3.64 ms` |
| Scoped retrieval over 1,000 records median | `7.39 ms` |
| Scoped retrieval over 1,000 records P95 | `8.47 ms` |

Current bottleneck:

Retrieval is linear over in-memory vectors. This is fine at small scale but will degrade as memory grows.

## Target Architecture

Introduce a layered RAG system:

```text
Query
  -> Query Router
  -> Hierarchical Retrieval
      -> namespace selection
      -> metadata prefilter
      -> vector candidate search
      -> rerank
      -> dedupe
      -> compression
  -> Context Bundle
```

Target components:

```text
rag/
├── query_router.py
├── hierarchical_retriever.py
├── chunker.py
├── dedupe.py
├── embedding_cache.py
├── reranker.py
├── context_compressor.py
└── stores.py
```

## Design Principles

1. Retrieve fewer records before scoring vectors.
2. Deduplicate chunks before indexing.
3. Cache embeddings by content hash.
4. Route queries to the smallest useful namespace.
5. Return compressed context, not raw memory dumps.
6. Preserve memory access controls and sensitivity filters.
7. Avoid duplicate indexing across repository, vault, and conversation memory.

## Hierarchical Retrieval

### Retrieval Levels

Use four levels:

```text
L0: Query classification
L1: Namespace and metadata routing
L2: Vector candidate retrieval
L3: Reranking and compression
```

### L0: Query Classification

Classify query intent:

- code/repository
- policy/security
- conversation/task history
- vault/secret reference
- operational/runtime
- agent behavior
- memory/RAG

Output:

```python
QueryProfile:
    intent: str
    namespaces: tuple[str, ...]
    required_filters: dict
    sensitivity_ceiling: str
    top_k_vector: int
    top_k_final: int
```

Example:

```text
Query: "Why did sandbox validation fail?"
Namespaces: repository, conversation
Filters: subsystem=sandbox
top_k_vector: 20
top_k_final: 5
```

### L1: Namespace and Metadata Routing

Route before vector search.

Namespaces:

| Namespace | Purpose | Collection |
| --- | --- | --- |
| `repository` | code, docs, architecture, tests | `anubis_repository_memory` |
| `conversation` | tasks, episodes, swarm/session output | `anubis_conversation_memory` |
| `vault` | secret references and restricted policy references | `anubis_vault_memory` |

Routing rules:

- Code/design query: `repository`
- Debug/runtime query: `conversation`, then `repository`
- Security policy query: `repository`, optionally `vault`
- Secret lookup: `vault` only, references only
- Agent history query: `conversation`

Metadata prefilters:

- `subsystem`
- `file_path`
- `scope_id`
- `run_id`
- `task_id`
- `agent`
- `sensitivity`
- `memory_kind`
- `source`

### L2: Vector Candidate Retrieval

Retrieve a wider candidate set than the final answer needs:

```text
top_k_vector = 20-50
top_k_final = 3-8
```

For current in-memory store:

- apply namespace and metadata filters first
- score only filtered candidates

For future Qdrant:

- use collection-level routing
- use payload filters before vector search
- use collection-specific limits

### L3: Reranking and Compression

Rerank candidates using:

- vector score
- exact keyword overlap
- recency
- source trust
- file/task proximity
- sensitivity allowance
- duplicate penalty

Final output should be compressed:

```python
RAGContext:
    chunks: tuple[ContextChunk, ...]
    summaries: tuple[CompressedSummary, ...]
    token_estimate: int
    excluded_duplicates: tuple[str, ...]
```

## Chunk Deduplication

### Chunk Identity

Every chunk gets a stable identity:

```text
chunk_id = sha256(namespace + source_uri + normalized_text)
content_hash = sha256(normalized_text)
semantic_hash = sha256(normalized_tokens_without_noise)
```

Use both:

- `content_hash` for exact duplicates
- `semantic_hash` for near-duplicates

### Deduplication Rules

Before indexing:

1. Normalize text.
2. Compute `content_hash`.
3. If `content_hash` already exists in namespace, skip indexing.
4. If `semantic_hash` already exists with same source, skip or merge metadata.
5. If same `chunk_id` exists with changed content, upsert.

During retrieval:

1. Group by `content_hash`.
2. Keep highest-scoring candidate.
3. Penalize same `source_uri` repeated chunks.
4. Limit chunks per source file/session.

Recommended limits:

```yaml
dedupe:
  max_chunks_per_file: 3
  max_chunks_per_session: 5
  exact_duplicate_policy: skip
  near_duplicate_policy: merge_metadata
```

### Chunk Metadata

```python
ChunkMetadata:
    chunk_id: str
    content_hash: str
    semantic_hash: str
    namespace: str
    source_uri: str
    source_type: str
    file_path: str | None
    run_id: str | None
    task_id: str | None
    agent: str | None
    token_count: int
    sensitivity: str
```

## Embedding Cache

### Purpose

Avoid recomputing embeddings for repeated text.

Current hashing embeddings are cheap, but a cache becomes essential if ANUBIS moves to model embeddings or Qdrant-backed retrieval.

### Cache Key

```text
embedding_cache_key = sha256(embedding_model + content_hash)
```

### Cache Record

```python
EmbeddingCacheRecord:
    key: str
    content_hash: str
    model: str
    dimensions: int
    vector: tuple[float, ...]
    created_at: datetime
    last_used_at: datetime
    hit_count: int
```

### Cache Policy

```yaml
embedding_cache:
  enabled: true
  max_records: 100000
  ttl_days: 30
  persist: true
  eviction: least_recently_used
```

### Cache Flow

```text
text
  -> normalize
  -> content_hash
  -> cache lookup
  -> hit: return vector
  -> miss: embed, store, return vector
```

Expected benefits:

- lower indexing latency for duplicate chunks
- lower CPU use
- less memory churn
- no repeated model embedding calls if model embeddings are introduced

## Query Routing

### Router Inputs

```python
QueryRequest:
    text: str
    actor_id: str
    task_type: str | None
    scope_ids: tuple[str, ...]
    allowed_namespaces: tuple[str, ...]
    max_sensitivity: str
    token_budget: int
```

### Router Outputs

```python
RoutedQuery:
    profile: QueryProfile
    collections: tuple[str, ...]
    filters: dict
    retrieval_plan: RetrievalPlan
```

### Routing Examples

Repository task:

```text
Input: "Refactor duplicated memory systems"
Route:
  namespaces: repository
  filters: subsystem in ["memory", "retrieval"]
  top_k_vector: 30
  top_k_final: 5
```

Conversation task:

```text
Input: "What did the previous run decide?"
Route:
  namespaces: conversation
  filters: run_id or task_id if available
  top_k_vector: 15
  top_k_final: 5
```

Security/vault task:

```text
Input: "Find the vault reference for production token"
Route:
  namespaces: vault
  filters: content_type=secret_reference
  top_k_vector: 10
  top_k_final: 3
```

Hybrid task:

```text
Input: "Why did plugin sandbox fail?"
Route:
  namespaces: conversation, repository
  filters:
    conversation: event_type=sandbox.denied
    repository: subsystem in ["plugins", "security"]
  top_k_vector: 40
  top_k_final: 6
```

## Token Usage Reduction

### Context Budgeting

RAG should produce context, not raw matches.

Suggested defaults:

```yaml
rag_context:
  max_chunks: 8
  max_tokens: 4000
  max_tokens_per_chunk: 500
  max_chunks_per_source: 3
  summary_when_over_tokens: true
```

### Compression Strategy

For each retrieved chunk:

1. Remove boilerplate.
2. Keep API names, file paths, and assertions.
3. Summarize repeated text.
4. Preserve security/policy conditions verbatim enough to act safely.
5. Attach source metadata.

Context output:

```text
Top Evidence
1. file/path.py: symbol summary
2. file/path_test.py: relevant assertions
3. config/policy.yaml: relevant policy keys

Compressed Notes
- duplicate memory paths exist in ...
- direct indexing occurs in ...
```

## Memory Consumption Reduction

Current issue:

- in-memory vector stores retain all vectors
- duplicated memory systems can index the same logical record multiple times

Optimizations:

1. Deduplicate before indexing.
2. Store one embedding per `content_hash`.
3. Store metadata references separately from vector data.
4. Use namespace-specific collections.
5. Evict or persist old conversation memory.
6. Avoid keeping both core and scoped vector stores for the same record.

Target memory model:

```text
Record store:
  canonical memory records

Chunk store:
  unique chunks and metadata

Embedding cache:
  one vector per content hash/model

Vector store:
  one point per chunk per namespace
```

## Latency Reduction

### Current Cost Drivers

- linear vector scan
- duplicate stores
- repeated embedding creation
- no namespace-first query routing
- no chunk/source limits before reranking

### Optimized Flow

```text
classify query
  -> route to 1-2 namespaces
  -> apply metadata filters
  -> embed query using cache
  -> retrieve top 20-50 candidates
  -> dedupe
  -> rerank
  -> compress to token budget
```

Expected target metrics:

| Metric | Current | Target |
| --- | ---: | ---: |
| Scoped retrieval P95 at 1k records | `8.47 ms` | `<6 ms` |
| Retrieval P95 at 10k records | Not measured | `<25 ms` |
| Retrieval P95 at 100k records | Not measured | `<100 ms` with Qdrant |
| Duplicate chunk indexing | Not tracked | `0 duplicates indexed` |
| Embedding cache hit rate | Not tracked | `>80%` for repeated repo/context tasks |
| Final RAG context size | Not bounded | `<4k tokens` default |

## Qdrant Integration Path

Qdrant is not currently present in the repository, but the optimized design should support it.

Collections:

```text
anubis_repository_memory
anubis_conversation_memory
anubis_vault_memory
```

Payload indexes:

- `namespace`
- `source_uri`
- `file_path`
- `scope_id`
- `run_id`
- `task_id`
- `agent`
- `sensitivity`
- `content_hash`
- `semantic_hash`
- `memory_kind`

Qdrant query strategy:

1. Choose collection from query router.
2. Apply payload filter.
3. Vector search with `top_k_vector`.
4. Merge candidates across collections.
5. Deduplicate by `content_hash`.
6. Rerank.
7. Compress.

## API Design

```python
class OptimizedRAGService:
    def index(self, document: RAGDocument) -> IndexResult:
        ...

    def query(self, request: QueryRequest) -> RAGContext:
        ...

    def reindex(self, namespace: str | None = None) -> ReindexReport:
        ...

    def cache_stats(self) -> EmbeddingCacheStats:
        ...
```

```python
class RAGDocument:
    namespace: str
    source_uri: str
    text: str
    metadata: dict
    sensitivity: str = "internal"
```

```python
class RAGContext:
    query: str
    route: RoutedQuery
    chunks: tuple[ContextChunk, ...]
    compressed_summary: str
    token_estimate: int
    retrieval_metrics: dict
```

## Migration Plan

### Phase 1: Consolidate Interfaces

Create one RAG service interface and adapters for:

- `core.memory.MemoryRetriever`
- `core.memory.VectorStore`
- `anubis.retrieval.QueryRouter`
- `SharedMemoryVectorDB`

Do not remove old systems yet.

### Phase 2: Add Chunk Deduplication

Add:

- chunk normalization
- `content_hash`
- `semantic_hash`
- dedupe ledger
- duplicate skip behavior

Add tests:

- exact duplicate chunks are indexed once
- metadata merges safely
- changed content upserts

### Phase 3: Add Embedding Cache

Add:

- cache key by model and content hash
- cache hit/miss metrics
- cache eviction policy

Add tests:

- repeated text uses cached embedding
- changed text gets new embedding
- model change invalidates cache

### Phase 4: Add Query Router

Add:

- query classification
- namespace routing
- metadata filter selection
- per-namespace top-k values

Add tests:

- repository queries do not search conversation by default
- vault queries never expose raw secrets
- hybrid queries search only requested namespaces

### Phase 5: Add Hierarchical Retrieval

Add:

- metadata prefilter
- vector candidate search
- dedupe
- rerank
- context compression

Add tests:

- final context respects token budget
- duplicate chunks do not appear in output
- source diversity is enforced

### Phase 6: Optional Qdrant Backend

Add Qdrant only after the in-memory optimized RAG service passes tests.

Add:

- Qdrant store adapter
- collection provisioning
- payload indexes
- local Docker Compose profile if needed

Keep in-memory backend for tests and offline runs.

## Rollback Strategy

Use backend flags:

```yaml
rag:
  optimized_enabled: false
  backend: in_memory
```

Rollback points:

- If dedupe breaks recall, disable dedupe and keep raw indexing.
- If embedding cache corrupts vectors, bypass cache.
- If query routing misses relevant results, fall back to all-namespace search.
- If Qdrant is unavailable, use in-memory backend.
- If compression loses critical context, return raw top chunks.

## Verification Metrics

Track per query:

- route selected
- collections searched
- candidate count before dedupe
- candidate count after dedupe
- cache hit/miss
- vector search latency
- rerank latency
- compression latency
- final token count
- result count

Example metrics:

```python
RAGMetrics:
    query_ms: float
    embedding_ms: float
    vector_search_ms: float
    rerank_ms: float
    compression_ms: float
    cache_hit: bool
    candidates_raw: int
    candidates_deduped: int
    tokens_out: int
```

## Optimization Priorities

1. Query routing before vector search.
2. Chunk deduplication before indexing.
3. Embedding cache.
4. Context compression.
5. Qdrant backend for scale.
6. Reranking improvements.

## Final Target

The optimized RAG architecture should retrieve less, score less, duplicate less, and emit less:

```text
small routed search
  -> deduped candidates
  -> cached embeddings
  -> compressed context
  -> lower latency, memory, and token usage
```

The most important design constraint is single-path indexing. Every memory system should call the same RAG service so duplicate chunks are not embedded or indexed multiple times.
