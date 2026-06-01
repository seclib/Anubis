---
name: knowledge_synthesis_skill
objective: Fuse retrieval and writing to turn evidence into durable structured knowledge.
dependencies:
  - retrieval_skill
  - writing_skill
---

# Knowledge Synthesis Skill

## Context
Use this fusion skill when retrieved evidence should become a note, documentation, memory entry, or reusable knowledge artifact.

## Procedure
1. Run `retrieval_skill` to collect relevant evidence.
2. Run `contextual_reasoning_skill` when evidence needs interpretation.
3. Run `writing_skill` to transform the evidence into a structured artifact.
4. Mark facts, inferences, decisions, and gaps clearly.
5. Store and index the artifact when it is durable.

## Expected Output
- Evidence summary
- Structured knowledge artifact
- Fact/inference separation when needed
- Storage and indexing result

