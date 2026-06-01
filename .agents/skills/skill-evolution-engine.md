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
3. DNA Encoding: encode the candidate or existing skill as `SKILL_DNA` before mutation or fusion.
4. Creation: write each new skill as Markdown with name, objective, procedure, context, dependencies, and expected output.
5. Mutation: improve triggers, steps, dependencies, or outputs when DNA fitness shows a fixable weakness.
6. Fusion: combine compatible skills when their procedures naturally reinforce each other.
7. Fitness: score utility, usage frequency, precision, and cost after creation or mutation.
8. Evolution Tree: update the skill graph with evolution edges (`A -> B`) and fusion edges (`A + B -> AB`).
9. Memory Injection: store the created or updated skill notes in durable memory and index them for retrieval.
10. Report created skills, mutations, fused skills, DNA changes, and tree updates.

## Expected Output
- New skills created
- SKILL_DNA encoded or updated
- Mutations applied
- Skills fused
- Evolution tree updated
