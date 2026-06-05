# ANUBIS Performance Audit

Date: 2026-06-05

## Summary

ANUBIS is currently fast for its active deterministic local workload. The active runtime is standard-library Python, in-memory, and does not call external model, vector database, network, or OS execution services in the measured path.

Main findings:

- Cold CLI startup median: `220.96 ms`.
- Peak startup RSS: `29.26 MB`.
- Existing Docker image size: `123.17 MB`.
- In-process graph bootstrap median after imports: `4.15 ms`.
- Core memory indexing median: `0.025 ms` per record.
- Core retrieval over `1,000` in-memory vectors median: `3.64 ms`.
- Scoped RAG retrieval over `1,000` in-memory vectors median: `7.39 ms`.
- Individual core agent execution is sub-millisecond.

The main performance risk is future scale, not current latency. Retrieval is currently linear in the number of in-memory vector records. There is no Qdrant or external vector DB in the current repository state.

## Methodology

Measurements were run locally from:

```text
/home/fatsio/AI/Anubis
```

Commands and techniques:

- Cold startup: repeated subprocess runs of `python3 bootstrap.py`.
- Startup memory: `/usr/bin/time -v`.
- Docker size: `docker image inspect anubis:local`.
- RAG/index/retrieval latency: local benchmark over existing `core.memory` and `anubis.retrieval` paths.
- Agent latency: direct calls to core `PlannerAgent`, `AnalystAgent`, `ExecutorAgent`, and `CriticAgent`.
- Sandbox latency: direct `SandboxRunner.run_task` benchmark.

Important limitation:

- Current RAG metrics measure in-memory deterministic vector stores, not Qdrant.
- Current agent metrics measure deterministic local agents, not LLM-backed agents.

## Current Metrics

### Startup Time

Cold subprocess startup:

| Metric | Value |
| --- | ---: |
| Iterations | 5 |
| Min | `214.67 ms` |
| Median | `220.96 ms` |
| Mean | `223.40 ms` |
| P95 | `241.61 ms` |
| Max | `241.61 ms` |

Single `/usr/bin/time -v` startup:

| Metric | Value |
| --- | ---: |
| Wall time | `0.25 s` |
| User time | `0.24 s` |
| System time | `0.01 s` |
| CPU | `99%` |

In-process bootstrap after imports:

| Metric | Value |
| --- | ---: |
| Iterations | 10 |
| Min | `3.95 ms` |
| Median | `4.15 ms` |
| Mean | `4.54 ms` |
| P95 | `6.52 ms` |
| Max | `6.52 ms` |

Interpretation:

- Most cold startup time is Python process/import cost.
- The graph runtime itself is lightweight once loaded.

### Memory Consumption

Startup process memory from `/usr/bin/time -v`:

| Metric | Value |
| --- | ---: |
| Maximum resident set size | `29,260 KB` / `28.57 MiB` |

Benchmark process RSS:

| Metric | Value |
| --- | ---: |
| Initial benchmark max RSS | `29,908 KB` / `29.21 MiB` |
| Max RSS after memory/RAG/agent benchmarks | `33,400 KB` / `32.62 MiB` |

Interpretation:

- Current single-run memory footprint is small.
- Memory grows modestly during synthetic indexing of `1,000+` records.
- Since all stores are in-memory, long-running or large-memory workloads will scale linearly unless a durable/vector backend is introduced.

### Docker Size

Existing local image:

| Metric | Value |
| --- | ---: |
| Image tag | `anubis:local` |
| Image ID prefix | `sha256:fd413731fe39e` |
| Image size | `123,169,581 bytes` / `123.17 MB` |
| Layers | `12` |
| Created | `2026-06-05T14:58:01.744205366+04:00` |

Application source copied into image:

| Area | Local Size |
| --- | ---: |
| `core` | `984 KB` |
| `src` | `1.4 MB` |
| `agents` | `64 KB` |
| `tests` | `456 KB` |
| `audit` | `80 KB` |

Docker history highlights:

- App source layers are small: `src` about `706 KB`, `core` about `491 KB`, `agents` about `17.8 KB`, `config` about `6.1 KB`.
- Image size is dominated by the pinned Python slim base image, not ANUBIS code.

### RAG Latency

Current RAG implementation:

- deterministic hashing embeddings
- in-memory vector stores
- cosine similarity
- linear scan over stored vectors
- no Qdrant integration in current repo state

Scoped RAG indexing:

| Metric | Value |
| --- | ---: |
| Records indexed during benchmark | `500` |
| Median per record | `0.034 ms` |
| Mean per record | `0.039 ms` |
| P95 per record | `0.055 ms` |
| Max per record | `0.382 ms` |

Scoped RAG retrieval over `1,000` records:

| Metric | Value |
| --- | ---: |
| Iterations | `300` |
| Min | `7.11 ms` |
| Median | `7.39 ms` |
| Mean | `7.52 ms` |
| P95 | `8.47 ms` |
| Max | `11.43 ms` |

Interpretation:

- Current latency is acceptable at `1,000` records.
- Retrieval will degrade linearly as memory grows.
- Scoped retrieval is slower than core retrieval because it applies access/isolation checks and route wrapping.

### Indexing Latency

Core memory indexing:

| Metric | Value |
| --- | ---: |
| Records indexed during benchmark | `500` |
| Median per record | `0.025 ms` |
| Mean per record | `0.027 ms` |
| P95 per record | `0.035 ms` |
| Max per record | `0.176 ms` |

Core retrieval over `1,000` indexed records:

| Metric | Value |
| --- | ---: |
| Iterations | `300` |
| Min | `3.53 ms` |
| Median | `3.64 ms` |
| Mean | `3.78 ms` |
| P95 | `4.60 ms` |
| Max | `5.89 ms` |

Interpretation:

- Indexing is extremely cheap because embedding is local token hashing.
- Retrieval is the bottleneck because it scores every vector.

### Retrieval Latency

Retrieval summary:

| Path | Indexed Records | Median | P95 |
| --- | ---: | ---: | ---: |
| `core.memory.MemoryManager.retrieve` | `1,000` | `3.64 ms` | `4.60 ms` |
| `anubis.retrieval.QueryRouter.query` scoped | `1,000` | `7.39 ms` | `8.47 ms` |

Interpretation:

- Core retrieval is faster because it has a narrower metadata/namespace path.
- Scoped retrieval is more policy-aware but roughly `2x` slower at the same record count.

### Agent Execution Latency

Direct core agent execution:

| Agent | Median | Mean | P95 | Max |
| --- | ---: | ---: | ---: | ---: |
| Planner | `0.054 ms` | `0.055 ms` | `0.063 ms` | `0.135 ms` |
| Analyst | `0.0058 ms` | `0.0059 ms` | `0.0064 ms` | `0.0209 ms` |
| Executor | `0.0041 ms` | `0.0041 ms` | `0.0044 ms` | `0.0107 ms` |
| Critic | `0.0075 ms` | `0.0077 ms` | `0.0086 ms` | `0.0242 ms` |

Sandbox runner:

| Metric | Value |
| --- | ---: |
| Median | `0.0299 ms` |
| Mean | `0.0309 ms` |
| P95 | `0.0338 ms` |
| Max | `0.1018 ms` |

Interpretation:

- Agent execution is not a current bottleneck.
- Planner is the slowest agent because it builds task graphs.
- Sandbox validation remains very cheap in the current authorization-only path.

## Target Metrics

Targets assume the current local deterministic architecture unless otherwise noted.

### Local CLI Runtime Targets

| Metric | Current | Target | Notes |
| --- | ---: | ---: | --- |
| Cold startup median | `220.96 ms` | `<200 ms` | Achievable by reducing import footprint and bytecode churn. |
| Cold startup P95 | `241.61 ms` | `<300 ms` | Already acceptable. |
| In-process bootstrap median | `4.15 ms` | `<5 ms` | Already meets target. |
| Peak startup RSS | `28.57 MiB` | `<35 MiB` | Already meets target. |
| Benchmark RSS after 1k vectors | `32.62 MiB` | `<50 MiB` | Already meets target. |

### Docker Targets

| Metric | Current | Target | Notes |
| --- | ---: | ---: | --- |
| Image size | `123.17 MB` | `<125 MB` near-term | Already meets near-term target. |
| Image size | `123.17 MB` | `<80 MB` long-term | Requires different base image strategy. |
| App source layer | ~`1.2 MB` | `<2 MB` | Already fine. |

### RAG and Retrieval Targets

| Metric | Current | Target | Notes |
| --- | ---: | ---: | --- |
| Core index median | `0.025 ms` | `<0.1 ms` | Already meets target. |
| Scoped index median | `0.034 ms` | `<0.2 ms` | Already meets target. |
| Core retrieval P95 at 1k records | `4.60 ms` | `<5 ms` | Already meets target. |
| Scoped retrieval P95 at 1k records | `8.47 ms` | `<10 ms` | Already meets target. |
| Retrieval P95 at 10k records | Not measured | `<25 ms` | Likely requires indexed/vector backend. |
| Retrieval P95 at 100k records | Not measured | `<100 ms` | Requires Qdrant or equivalent. |

### Agent Targets

| Metric | Current | Target | Notes |
| --- | ---: | ---: | --- |
| Planner P95 | `0.063 ms` | `<1 ms` | Already meets target. |
| Executor P95 | `0.0044 ms` | `<1 ms` | Already meets target. |
| Reviewer/Critic P95 | `0.0086 ms` | `<1 ms` | Already meets target. |
| Sandbox runner P95 | `0.0338 ms` | `<1 ms` | Already meets target. |

## Optimization Opportunities

### 1. Replace Linear Vector Search at Scale

Current state:

- Retrieval scores every vector in memory.
- This is fine at `1,000` records but will not scale cleanly.

Opportunity:

- Introduce one unified memory service with Qdrant-backed collections when memory grows.
- Keep no-duplicate-indexing ledger so records are not indexed multiple times.
- Use separate collections for repository, vault, and conversation memory if that target architecture is adopted.

Expected impact:

- Better retrieval latency at `10k+` and `100k+` records.
- Better memory behavior for long-running sessions.

Risk:

- Adds external service dependency and Docker/runtime complexity.

### 2. Unify Duplicate Memory/RAG Paths

Current state:

- `core.memory` and `anubis.memory` both define memory/retrieval/vector concepts.
- Core retrieval is faster but less policy-rich.
- Scoped retrieval is richer but slower.

Opportunity:

- Use one memory API and one indexing path.
- Keep access-control and sensitivity filtering in the shared service.
- Avoid duplicate indexing between episodic, semantic, swarm, and future conversation memory.

Expected impact:

- Lower indexing overhead when multiple memory systems write the same event.
- Easier retrieval benchmarking and tuning.

Risk:

- Medium to high migration risk because memory tests cover several behavior variants.

### 3. Simplify Agent Architecture

Current state:

- Core graph has planner/analyst/executor/critic.
- Living runtime has watcher/thinker/executor/healer/predator.
- Research swarm has planner/executor/analyst/critic/synthesizer.

Opportunity:

- Collapse public roles to Planner, Executor, Reviewer.
- Preserve sub-behaviors as modes or internal helpers.
- Remove mandatory consensus layers where Reviewer can produce a deterministic decision.

Expected impact:

- Less orchestration overhead.
- Smaller import/runtime surface.
- Less duplicated reasoning.

Risk:

- Research swarm tests currently expect five roles, so migration needs compatibility wrappers.

### 4. Reduce Cold Startup Imports

Current state:

- Cold startup median is `220.96 ms`.
- In-process bootstrap after imports is only `4.15 ms`.

Opportunity:

- Audit import chains from `bootstrap.py`.
- Defer optional living-loop, research swarm, plugin, and evolution imports from active graph bootstrap.
- Keep CLI bootstrap focused on `core.graph`.

Expected impact:

- Cold startup closer to `<200 ms`.

Risk:

- Low if imports are moved lazily without behavior changes.

### 5. Remove Generated Bytecode and Tool Caches from Repo

Current state:

- Prior dependency cleanup audit estimated about `1.06 MiB` of bytecode/cache cleanup opportunity.
- Running Python commands can dirty tracked `__pycache__` files.

Opportunity:

- Remove tracked bytecode.
- Ensure ignore rules cover generated caches.

Expected impact:

- Cleaner verification.
- Less noisy performance runs.
- Small disk savings.

Risk:

- Low.

### 6. Docker Image Base Strategy

Current state:

- Image is `123.17 MB`.
- App layers are small; base image dominates.

Opportunity:

- Keep current image for safety and reproducibility.
- If long-term target is `<80 MB`, evaluate a smaller Python base or distroless-style runtime.

Expected impact:

- Potential 30-50 MB reduction depending on base.

Risk:

- Medium. Smaller images can complicate debugging, certificates, timezone data, and Python shared library behavior.

### 7. Add Performance Regression Tests

Current state:

- No formal benchmark suite exists.

Opportunity:

- Add a local benchmark script with thresholds for:
  - cold startup
  - graph bootstrap
  - indexing 1k records
  - retrieval over 1k records
  - agent execution

Expected impact:

- Prevent accidental regressions during cleanup.

Risk:

- Low, if thresholds are generous and not used as brittle CI gates initially.

## Bottleneck Assessment

| Area | Current Bottleneck? | Reason |
| --- | --- | --- |
| Startup | Mild | Cold import/process cost dominates. |
| Memory | No at current scale | RSS remains under `35 MiB` in measured workload. |
| Docker size | No near-term | Image already about `123 MB`; app layers are tiny. |
| Indexing | No | Hashing embedder is extremely cheap. |
| Retrieval | Future bottleneck | Linear scan will scale poorly beyond small memory sets. |
| Agent execution | No | Deterministic agents are sub-millisecond. |
| Sandbox runner | No | Authorization-only path is sub-millisecond. |

## Recommended Next Steps

1. Keep current performance baseline as the reference for cleanup work.
2. Add a benchmark script under `tools/` or `scripts/` before large refactors.
3. Prioritize memory/RAG unification before adding Qdrant.
4. Introduce Qdrant only after the unified memory service has a single indexing API.
5. Collapse agent roles before optimizing agent latency; current latency is already excellent.
6. Optimize cold imports only after architecture simplification removes duplicate runtime paths.

## Final Assessment

ANUBIS is currently performance-light and bottleneck-free for deterministic local runs. The strongest optimization opportunity is architectural: remove duplicate memory and agent paths so future RAG, Qdrant, and agent workflows do not multiply indexing, retrieval, and orchestration costs.
