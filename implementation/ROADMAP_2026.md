🚀 SPRINT 1 — FULL AUDIT

PROMPT S1-A

You are acting as a Principal Software Architect.

Perform a complete repository audit of Anubis.

Your mission is NOT to add features.

Your mission is to understand the current state of the project.

Analyze:

- repository structure
- architecture
- dependencies
- services
- Docker
- Tauri
- Python environment
- memory systems
- RAG systems
- agent systems
- git integration
- configuration files

Generate:

audit/
├── architecture_audit.md
├── dependency_audit.md
├── service_inventory.md
├── performance_baseline.md
├── technical_debt.md
└── risk_assessment.md

Do not modify code.

Audit only.

PROMPT S1-B

Perform a dead-code and duplication audit.

Identify:

- duplicate modules
- duplicate services
- duplicate prompts
- duplicate memory systems
- duplicate agent logic
- unused files
- obsolete code

Classify every finding:

KEEP
MERGE
REFACTOR
DEPRECATE
REMOVE

Output:

audit/duplication_audit.md

No code modifications.

PROMPT S1-C

Perform a dependency audit.

Analyze:

Python:
- unused packages
- oversized packages
- duplicate dependencies

Node:
- unused packages
- build dependencies
- runtime dependencies

Rust:
- unnecessary crates

Output:

audit/dependency_cleanup.md

Include:
- estimated disk savings
- risk level
- migration recommendations

Do not uninstall anything.

🚀 SPRINT 2 — CLEANUP

PROMPT S2-A

Using audit results only.

Generate a cleanup plan.

Goals:

- remove dead code
- remove obsolete services
- remove duplicated functionality
- simplify architecture

Requirements:

- preserve functionality
- produce migration steps
- identify rollback strategy

Output:

cleanup_plan.md

Do not execute changes.

PROMPT S2-B

Refactor duplicated memory systems.

Goal:

Create one Unified Memory Service.

Merge:

- repository memory
- vault memory
- conversation memory

Requirements:

- shared API
- Qdrant collections
- no duplicate indexing

Output:

implementation plan
migration plan

PROMPT S2-C

Analyze all agent systems.

Identify:

- redundant agents
- overlapping responsibilities
- duplicated reasoning layers

Target architecture:

Planner
Executor
Reviewer

Generate:

agent_simplification.md

No implementation yet.

🚀 SPRINT 3 — PERFORMANCE

PROMPT S3-A

Perform a performance audit.

Measure:

- startup time
- memory consumption
- Docker size
- RAG latency
- indexing latency
- retrieval latency
- agent execution latency

Generate:

performance_audit.md

Include:

current metrics
target metrics
optimization opportunities

PROMPT S3-B

Design a Context Builder.

Goal:

Reduce token usage.

Requirements:

- relevance ranking
- file ranking
- token budgeting
- context compression

Target:

Only 3-5 files per task.

Output:

context_builder_design.md

PROMPT S3-C

Optimize RAG architecture.

Current goal:

Reduce:
- latency
- memory consumption
- token usage

Implement design only.

Requirements:

- hierarchical retrieval
- chunk deduplication
- embedding cache
- query routing

Generate:

rag_optimization_plan.md

PROMPT S3-D

Audit Docker architecture.

Analyze:

- image sizes
- layer duplication
- cache usage
- build strategy

Goal:

Reduce image sizes by 70%.

Generate:

docker_optimization.md


🚀 SPRINT 4 — PRODUCT

PROMPT S4-A

Audit user experience.

Compare Anubis against:

- Claude Code
- Codex
- Cursor

Identify gaps.

Focus:

- workflow
- ergonomics
- usability
- speed

Output:

product_gap_analysis.md

PROMPT S4-B

Design professional workspace architecture.

Target layout:

Left:
- repository explorer
- vault
- git

Center:
- conversation

Bottom:
- terminal

Right:
- execution panel
- memory references

Generate:

workspace_design.md

PROMPT S4-C

Design native Git experience.

Requirements:

- branch creation
- diff viewer
- commit workflow
- PR workflow

Benchmark:

Claude Code
Cursor

Output:

git_experience_design.md

PROMPT S4-D

Design integrated terminal architecture.

Requirements:

- streaming output
- sandbox awareness
- execution logs
- command history

Generate:

terminal_design.md


🚀 SPRINT 5 — PRODUCTION HARDENING

Seulement après que tout fonctionne.

PROMPT S5-A

Design production observability.

Requirements:

- metrics
- tracing
- logs
- health checks

Generate:

observability_plan.md

PROMPT S5-B

Design production security layer.

Requirements:

- sandboxing
- filesystem isolation
- network isolation
- permission system

Generate:

security_architecture.md

PROMPT S5-C

Design AI SOC architecture.

Requirements:

- monitoring
- anomaly detection
- incident tracking
- alerting

Generate:

soc_design.md

PROMPT S5-D

Design Autonomous Red Team system.

Requirements:

- attack simulation
- sandbox execution
- exploit analysis
- patch recommendation

Generate:

red_team_design.md
