---
name: skill-evolution-engine
objective: Detect repeated agentic patterns and turn them into reusable, actionable Anubis skills.
dependencies:
  - loop-cognition-core
  - obsidian-markdown-memory
  - qdrant-indexing
---

# Skill Evolution Engine

## Context
Anubis should evolve by creating, merging, and refining skills instead of letting useful procedures remain implicit in chat history or scattered notes.

## Procedure
1. Detection: inspect recent memory, notes, repository conventions, and repeated actions for reusable patterns.
2. Qualification: keep only patterns that are action-oriented, reusable, and likely to improve future work.
3. Creation: write each new skill as Markdown with name, objective, procedure, context, dependencies, and expected output.
4. Fusion: combine compatible skills when their procedures naturally reinforce each other.
5. Evolution Tree: update the skill graph with evolution edges (`A -> B`) and fusion edges (`A + B -> AB`).
6. Memory Injection: store the created or updated skill notes in durable memory and index them for retrieval.
7. Report created skills, fused skills, and tree updates.

## Expected Output
- New skills created
- Skills fused
- Evolution tree updated

