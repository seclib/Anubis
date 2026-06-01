---
name: advanced_rag_skill
objective: Build higher-quality retrieval-augmented context using query planning, hybrid retrieval, filtering, and confidence checks.
dependencies:
  - retrieval_skill
---

# Advanced RAG Skill

## Context
Use this skill when simple recall is not enough and the task needs multi-source grounding, query rewriting, or confidence-aware synthesis.

## Procedure
1. Analyze the task and rewrite the query for retrieval.
2. Expand entities, keywords, and constraints.
3. Retrieve through hybrid channels: Qdrant/vector, keyword index, Markdown notes, and cache.
4. Apply metadata filters such as domain, source type, quality, or freshness.
5. Merge and rank evidence with explicit confidence.
6. Return only evidence that can support the next action.

## Expected Output
- Query plan
- Ranked evidence set
- Confidence level
- Gaps or need for additional retrieval

