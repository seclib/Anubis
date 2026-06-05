# ANUBIS Context Builder Design

Date: 2026-06-05

## Goal

Design a Context Builder that reduces token usage by selecting only the most relevant repository context for a task.

Target:

```text
3-5 files per task
```

The Context Builder should rank files, enforce token budgets, compress context, and avoid dumping broad repository state into prompts.

## Problem

ANUBIS has multiple overlapping systems:

- graph runtime
- living runtime
- memory/RAG systems
- agent systems
- plugin systems
- security systems
- observability systems

Many tasks only need a small slice of the repository. Without a Context Builder, agents may read too many files, duplicate context, and carry unrelated architecture history into the task.

## Design Principles

1. Prefer precision over recall.
2. Select files before reading full content.
3. Rank by task relevance, not directory popularity.
4. Preserve enough context to make safe edits.
5. Compress aggressively after evidence is gathered.
6. Never include generated files, caches, or bytecode.
7. Keep the final context set to 3-5 files unless the task is explicitly cross-cutting.

## High-Level Flow

```text
Task
  -> Task Classifier
  -> Candidate Discovery
  -> File Ranking
  -> Token Budget Planner
  -> Context Compressor
  -> Final Context Bundle
```

## Components

### 1. Task Classifier

Purpose:

Classify the task so ranking can prioritize the right subsystem.

Task categories:

- architecture audit
- code edit
- bug fix
- memory/RAG work
- agent work
- Docker/runtime work
- security/sandbox work
- plugin work
- test failure
- documentation

Output:

```python
TaskProfile:
    task_type: str
    target_subsystems: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    requires_tests: bool
    requires_configs: bool
    max_files: int = 5
```

Example:

```text
Task: "Refactor duplicated memory systems"
Subsystems: memory, retrieval, graph memory node, tests
Max files: 5
```

### 2. Candidate Discovery

Purpose:

Find potentially relevant files without reading the whole repository.

Signals:

- filename match
- symbol match
- import graph proximity
- test file pairing
- audit finding references
- config references
- recent touched files
- docs references when task is architecture/design

Discovery commands:

```bash
rg --files
rg -n "<task keywords>"
```

Candidate metadata:

```python
FileCandidate:
    path: str
    subsystem: str
    matched_terms: tuple[str, ...]
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    paired_tests: tuple[str, ...]
    estimated_tokens: int
```

Excluded by default:

- `__pycache__/`
- `.ruff_cache/`
- `.git/`
- generated artifacts
- audit outputs unless task asks for audit-derived context
- huge files unless specifically targeted

### 3. File Ranking

Purpose:

Score each candidate and select only the highest-value files.

Ranking factors:

| Signal | Weight | Reason |
| --- | ---: | --- |
| Direct path/name match | High | User likely named or implied target. |
| Symbol/class/function match | High | Strong implementation relevance. |
| Import dependency proximity | Medium | Needed to understand contracts. |
| Paired test file | Medium | Needed for behavior preservation. |
| Config reference | Medium | Needed for runtime policy tasks. |
| Recent audit reference | Medium | Useful for cleanup/refactor tasks. |
| File size penalty | Medium | Large files consume budget quickly. |
| Generated/cache file | Exclude | Never useful. |

Score formula:

```text
score =
  direct_match * 5
  + symbol_match * 4
  + import_proximity * 3
  + paired_test * 3
  + config_relevance * 2
  + audit_reference * 2
  - size_penalty
```

### 4. Token Budget Planner

Purpose:

Ensure selected files fit the task budget.

Default budget:

```text
Total context budget: 12k tokens
File content budget: 8k tokens
Summaries budget: 2k tokens
Tests/config budget: 2k tokens
```

For normal code tasks:

```text
3 implementation files
1 paired test file
1 config/doc file if relevant
```

Budget rules:

- If a file is under budget, include relevant sections or full file.
- If a file is large, include only symbol-relevant ranges.
- If more than 5 files score highly, compress lower-ranked files into summaries.
- If the task is design-only, prefer audits/docs over implementation files.
- If the task is implementation, prefer code/tests over docs.

Target selection:

```python
ContextBundle:
    primary_files: 3-5
    compressed_summaries: 0-3
    excluded_relevant_files: tuple[str, ...]
    token_budget_used: int
```

### 5. Context Compression

Purpose:

Preserve meaning while removing token-heavy detail.

Compression methods:

- symbol summaries
- responsibility summaries
- API signatures
- call-chain summaries
- behavior/test summaries
- config key summaries
- deduplicated repeated text

Compression output format:

```text
File: core/memory/memory_manager.py
Relevant symbols:
- MemoryManager.append_episode(...)
- MemoryManager.append_fact(...)
- MemoryManager.retrieve(...)
Key behavior:
- appends episodic/semantic records
- indexes through vector_store when index=True
- retrieval delegates to MemoryRetriever
Risk:
- duplicate indexing path with anubis.retrieval
```

Do not compress away:

- public API signatures
- class names
- enum values
- validation rules
- security gates
- test assertions
- migration-sensitive behavior

## File Selection Strategy

### Code Edit Task

Select:

1. primary implementation file
2. direct dependency/contract file
3. paired test file
4. config file if behavior is config-driven
5. related adapter/caller

Example for memory refactor:

```text
src/anubis/memory.py
src/anubis/retrieval.py
core/memory/memory_manager.py
core/graph/nodes.py
tests/test_memory.py or tests/test_core_memory.py
```

### Agent Task

Select:

```text
core/agents/registry.py
core/agents/base_agent.py
target agent file
src/anubis/life_cycle/boot_sequence.py
tests/test_core_agents.py or tests/test_research_swarm.py
```

### Docker Task

Select:

```text
Dockerfile
docker-compose.yml
config/production_hardening.yaml
docs/docker_runtime_security.md
.github/workflows/security-pipeline.yml
```

### Security Task

Select:

```text
core/security/security_kernel.py
core/security/sandbox_guard.py
core/security/permission_engine.py
config/permissions.yaml
tests/test_core_security.py
```

## Relevance Ranking Example

Task:

```text
Design a Context Builder to reduce token usage.
```

Likely top files:

| Rank | File | Reason |
| ---: | --- | --- |
| 1 | `cleanup_plan.md` | Defines cleanup/migration context. |
| 2 | `audit/duplication_audit.md` | Identifies duplicate systems that cause context bloat. |
| 3 | `audit/architecture_audit.md` | Defines active vs secondary runtime. |
| 4 | `agent_simplification.md` | Agent simplification context. |
| 5 | `performance_audit.md` | Token/context efficiency ties to performance. |

Because this is a design task, implementation files are less relevant than audit/design files.

## Context Bundle Format

Final context should be structured:

```text
Task Profile
- type
- subsystem
- max files
- token budget

Selected Files
1. path
   reason
   token estimate
   included sections

Compressed Context
- file summaries
- key APIs
- risks
- tests to preserve

Excluded But Relevant
- path: reason excluded
```

## API Design

```python
class ContextBuilder:
    def build(self, task: str, *, max_files: int = 5, token_budget: int = 12000) -> ContextBundle:
        ...

    def discover(self, profile: TaskProfile) -> tuple[FileCandidate, ...]:
        ...

    def rank(self, task: str, candidates: tuple[FileCandidate, ...]) -> tuple[RankedFile, ...]:
        ...

    def compress(self, files: tuple[RankedFile, ...], budget: TokenBudget) -> ContextBundle:
        ...
```

## Data Structures

```python
class RankedFile:
    path: str
    score: float
    reasons: tuple[str, ...]
    estimated_tokens: int
    include_mode: Literal["full", "sections", "summary"]

class TokenBudget:
    total: int
    file_content: int
    summaries: int
    reserve: int

class ContextBundle:
    task_profile: TaskProfile
    files: tuple[RankedFile, ...]
    summaries: tuple[FileSummary, ...]
    excluded: tuple[ExcludedFile, ...]
    token_estimate: int
```

## Token Budgeting Rules

Hard rules:

- Never exceed task budget.
- Never include more than 5 full/section files by default.
- Reserve at least 20 percent for reasoning and answer generation.
- Prefer summaries over extra files.

Soft rules:

- If implementation file exceeds 2,500 tokens, include sections.
- If test file exceeds 2,000 tokens, include relevant test functions.
- If docs/audits exceed 2,000 tokens, summarize.
- If a file scores below threshold, exclude it even if budget remains.

## Compression Heuristics

For Python files:

- include imports only if they define dependencies
- include class/function signatures
- include validation branches
- include public methods
- summarize private helpers
- omit repeated dataclass boilerplate unless relevant

For tests:

- include test names
- include assertions
- summarize setup fixtures
- omit unrelated tests

For config:

- include relevant keys only
- summarize unrelated policy sections

For audits/docs:

- include conclusions and classified findings
- omit repeated background

## Handling Large Modules

Large modules identified in audits:

- `src/anubis/swarm.py`
- `src/anubis/memory.py`
- `src/anubis/plugins.py`
- `core/graph/runner.py`
- `src/anubis/planner.py`

Rule:

Do not include these whole files by default.

Use:

- symbol extraction
- section summaries
- targeted line ranges
- paired tests for behavioral intent

## Integration With ANUBIS Agents

The Context Builder should run before agent execution.

Target agent flow:

```text
User Task
  -> Context Builder
  -> Planner receives compact context bundle
  -> Executor receives selected files only
  -> Reviewer receives diff + tests + compressed source context
```

Planner needs:

- task profile
- selected files
- architectural constraints

Executor needs:

- exact file sections
- tests/configs
- migration constraints

Reviewer needs:

- changed files
- preserved behavior checklist
- relevant tests

## Avoiding Context Duplication

Deduplication rules:

- If two files expose the same API, include canonical file and summarize duplicate.
- If an audit already summarizes a subsystem, do not include every subsystem file for design tasks.
- If a wrapper delegates to another module, include the target module and summarize wrapper.
- If tests duplicate behavior, include the most direct test file.

Example:

For agent simplification, do not include every agent file. Include:

```text
core/agents/base_agent.py
core/agents/registry.py
src/anubis/life_cycle/boot_sequence.py
agents/base.py
tests/test_core_agents.py
```

Summarize individual agent implementations.

## Metrics

Track:

- selected file count
- estimated input tokens
- actual input tokens
- files excluded
- compression ratio
- task success
- test pass/fail after context use

Target metrics:

| Metric | Target |
| --- | ---: |
| Files per task | `3-5` |
| Context token reduction | `50-80%` |
| Relevant file recall | `>=90%` for implementation tasks |
| Irrelevant file inclusion | `<20%` |
| Full large-file inclusion | `0` by default |

## Failure Modes

| Failure | Mitigation |
| --- | --- |
| Important file excluded | Keep excluded-relevant list and allow second-pass expansion. |
| Too many files selected | Apply size penalty and subsystem cap. |
| Large file consumes budget | Switch to section mode. |
| Wrapper selected instead of implementation | Follow imports and delegation. |
| Tests omitted | Always reserve test/config slot for code edits. |
| Audit summaries become stale | Prefer live code for implementation tasks. |

## Recommended Defaults

```yaml
context_builder:
  max_files: 5
  default_files: 4
  token_budget: 12000
  reserve_tokens: 2500
  max_full_file_tokens: 2500
  max_test_tokens: 2000
  compression_target: 0.5
  exclude:
    - __pycache__
    - .ruff_cache
    - .git
    - node_modules
    - target
```

## Rollout Plan

Phase 1:

- Implement candidate discovery and ranking.
- Output selected files only.
- No compression yet.

Phase 2:

- Add token estimates.
- Add hard 3-5 file cap.
- Add excluded-relevant reporting.

Phase 3:

- Add compression summaries.
- Add section extraction for large Python files.

Phase 4:

- Integrate with Planner/Executor/Reviewer flow.
- Track metrics per task.

Phase 5:

- Add feedback loop from test failures to expand context.

## Final Target

The Context Builder should make ANUBIS task execution feel focused:

```text
one task -> one ranked context bundle -> 3-5 files -> compressed supporting summaries
```

This will reduce token usage, reduce duplicated reasoning, and make future agent execution easier to control.
