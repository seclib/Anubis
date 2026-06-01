---
name: retrieval_skill
objective: Retrieve relevant knowledge from Anubis memory, notes, vector search, and Qdrant before reasoning or acting.
dependencies:
  - loop-cognition-core
---

# Retrieval Skill

## Context
Use this skill when an agent needs grounded context from local memory, Markdown notes, repository vectors, or Qdrant.

## Procedure
1. Define the retrieval query from the user task and current goal.
2. Search Hermes memory, Obsidian/Markdown notes, local vector memory, and Qdrant when available.
3. Rank results by relevance, confidence, recency, and source diversity.
4. Remove duplicates, weak matches, and raw dumps.
5. Produce a concise context block for downstream reasoning.

## Expected Output
- Retrieval query
- Relevant memory/context bullets
- Sources or artifact paths when useful
- Confidence or weakness signal

