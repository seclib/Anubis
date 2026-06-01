---
name: meta-cognition-agent
objective: Observe and analyze Anubis agents without directly executing their workflows, producing structural insights about decisions, inefficiencies, bias, redundancy, and memory flow.
dependencies:
  - retrieval_skill
  - writing_skill
  - skill-evolution-engine
  - infinite-loop-optimizer
  - skill-dna-engine
---

# Meta-Cognition Agent

## Context
Use this skill when Anubis needs a reflective system-level report about how its agents behave. This agent observes `retriever_agent`, `writer_agent`, `indexer_agent`, `skill_engine`, and `loop_optimizer`; it does not execute their work directly.

## Procedure
1. Observation: collect traces, memory summaries, skill DNA, evolution-tree edges, retrieval confidence, indexing outcomes, and loop diagnostics.
2. Pattern Analysis: identify repeated decisions, agent handoffs, missing verification, duplicated responsibilities, high-cost paths, and recurring failure modes.
3. Decision Quality Review: compare outputs against evidence quality, memory eligibility, validation status, and downstream usefulness.
4. Redundancy Check: detect agents or skills whose triggers, steps, or outputs overlap enough to merge or clarify ownership.
5. Architecture Reflection: identify changes that would improve global learning, memory flow, skill evolution, and loop stability.
6. Restructuring Suggestions: propose new agents, workflow changes, memory-flow changes, or Skill DNA mutations.
7. Report: produce insights only; do not call retriever/writer/indexer/optimizer as execution delegates.

## Observation Scope
- `retriever_agent`: retrieval confidence, source diversity, weak or noisy context, RAG conflict.
- `writer_agent`: note structure, factual density, durable memory quality, duplication risk.
- `indexer_agent`: indexing success, stale documents, Qdrant/vector consistency, retrieval freshness.
- `skill_engine`: skill creation quality, fusion quality, DNA registry health, weak-skill handling.
- `loop_optimizer`: repeated actions, invalid outputs, recursion depth, stabilization choices.

## Expected Output
- System cognition report
- Problems detected
- Proposed improvements
- Suggested restructuring or Skill DNA mutations

