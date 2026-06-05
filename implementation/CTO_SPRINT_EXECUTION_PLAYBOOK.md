# ANUBIS — CTO SPRINT EXECUTION PLAYBOOK (CODEX READY)

Version: Production Refactor Plan

---

# 🧠 PRINCIPLE

This plan is designed for a senior engineering team (CTO, Staff Engineers, Principal Engineers).

Core philosophy:

> Do not build more.
> First make the system smaller, faster, and understandable.

---

# 🚀 SPRINT 1 — SYSTEM VISIBILITY (AUDIT FIRST)

## Goal

Build complete understanding of Anubis before changing anything.

---

## PROMPT S1-1 — FULL SYSTEM MAPPING

```text
You are a Principal Engineer.

Task:
Create a full system map of Anubis.

Include:
- services
- agents
- memory systems
- RAG pipelines
- Docker architecture
- frontend/backend separation
- dependencies

Output:
system_map.md

NO CODE CHANGES.
```

---

## PROMPT S1-2 — PERFORMANCE BASELINE

```text
Analyze system performance.

Measure:
- startup time
- memory usage
- Docker size
- agent latency
- RAG latency
- LLM call frequency

Output:
performance_baseline.md

NO MODIFICATIONS.
```

---

## PROMPT S1-3 — DEPENDENCY & SIZE AUDIT

```text
Audit dependencies.

Include:
- Python (.venv)
- Node modules
- Rust/Tauri build
- Docker images

Identify:
- largest packages
- unused dependencies
- duplication

Output:
dependency_audit.md

NO REMOVALS.
```

---

# 🧹 SPRINT 2 — REDUCTION (REMOVE COMPLEXITY)

## PROMPT S2-1 — DEAD CODE ANALYSIS

```text
Identify dead or unused code in Anubis.

Find:
- unused modules
- duplicate services
- legacy agents
- obsolete RAG systems

Classify:
KEEP / REMOVE / MERGE / REFACTOR

Output:
cleanup_candidates.md

NO DELETION.
```

---

## PROMPT S2-2 — AGENT SIMPLIFICATION

```text
Simplify agent system.

Current likely state:
- too many overlapping agents

Target:
Planner
Executor
Reviewer

Output:
agent_simplification_plan.md

NO CODE CHANGES.
```

---

## PROMPT S2-3 — MEMORY UNIFICATION

```text
Analyze all memory systems.

Goal:
Merge into ONE unified memory system using Qdrant.

Identify:
- duplicates
- overlapping indexes
- redundant pipelines

Output:
memory_unification_plan.md
```

---

# ⚙️ SPRINT 3 — PERFORMANCE ENGINEERING

## PROMPT S3-1 — CONTEXT REDUCTION ENGINE

```text
Design Context Builder for Anubis.

Goal:
Reduce LLM context size drastically.

Rules:
- only 3–5 files per task
- relevance ranking required
- token budget enforced

Output:
context_builder_design.md
```

---

## PROMPT S3-2 — RAG OPTIMIZATION

```text
Optimize RAG system.

Goals:
- reduce latency
- reduce token usage
- reduce redundant retrieval

Add:
- hierarchical retrieval
- embedding cache
- top-k tuning
- query routing

Output:
rag_optimization_plan.md
```

---

## PROMPT S3-3 — DOCKER OPTIMIZATION

```text
Optimize Docker architecture.

Goal:
Reduce image size by at least 70%.

Actions:
- multi-stage builds
- remove dev dependencies
- isolate runtime
- reduce layers

Output:
docker_optimization_plan.md
```

---

# 🧱 SPRINT 4 — PRODUCT SIMPLIFICATION

## PROMPT S4-1 — UX GAP ANALYSIS

```text
Compare Anubis with:
- Claude Code
- Cursor
- Codex

Find missing features:
- workflow gaps
- UX friction
- performance issues

Output:
product_gap_analysis.md
```

---

## PROMPT S4-2 — WORKSPACE DESIGN

```text
Design professional developer workspace.

Layout:
- left: repo + vault + git
- center: chat
- bottom: terminal
- right: tasks + memory

Output:
workspace_design.md
```

---

## PROMPT S4-3 — GIT INTEGRATION DESIGN

```text
Design native Git workflow.

Features:
- diff viewer
- commit generation
- branch management
- PR preparation

Output:
git_integration_design.md
```

---

## PROMPT S4-4 — TERMINAL SYSTEM

```text
Design integrated terminal system.

Requirements:
- streaming logs
- sandbox execution
- command history
- agent visibility

Output:
terminal_design.md
```

---

# 🔒 SPRINT 5 — HARDENING (ONLY AFTER STABILITY)

## PROMPT S5-1 — OBSERVABILITY SYSTEM

```text
Design full observability system.

Include:
- logs
- metrics
- traces
- system health

Output:
observability_plan.md
```

---

## PROMPT S5-2 — SECURITY ARCHITECTURE

```text
Design security layer for Anubis.

Include:
- sandboxing
- filesystem isolation
- permission system
- network control

Output:
security_architecture.md
```

---

## PROMPT S5-3 — AI SOC DESIGN

```text
Design Security Operation Center (SOC) for agents.

Features:
- anomaly detection
- event monitoring
- incident tracking
- kill switch system

Output:
soc_design.md
```

---

## PROMPT S5-4 — RED TEAM SYSTEM

```text
Design autonomous Red Team system.

Goal:
Simulate attacks inside sandbox to test system robustness.

Include:
- attack simulation
- exploit detection
- defense evaluation

Output:
red_team_design.md
```

---

# 🧭 EXECUTION RULE (IMPORTANT)

Execution order:

```text
S1 → S2 → S3 → S4 → S5
```

Never skip S1 or S2.

---

# ⚠️ CTO RULE

If the system is still:

* slow
* heavy
* duplicated
* unclear

DO NOT add features.

Only reduce complexity.

---

# 🧠 FINAL INTENT

Transform Anubis into:

* fast system
* minimal architecture
* production-grade stability
* clean separation of concerns

Before any scaling or advanced AI features.
