---
title: The user defines Anubis as a Loop Cognition Core that must run MEMORY -> ACTION -> NEW MEMORY for every interaction.
created: 2026-06-01T05:59:40.351912+00:00
type: knowledge
rag_ready: true
tags:
  - hermes
---

# The user defines Anubis as a Loop Cognition Core that must run MEMORY -> ACTION -> NEW MEMORY for every interaction.

- Created: 2026-06-01T05:59:40.293720+00:00
- Tags: loop-cognition-core, memory-action-new-memory, rag, qdrant, obsidian, agent-policy, continuous-learning, user-preference, high

## Task
Adopt Loop Cognition Core operating contract

## Result
Anubis interactions should retrieve RAG/Qdrant and Markdown memory first, decide an action, execute through available agents/tools, then write structured durable memory and index it back into retrieval when possible.

## Lessons
- Every non-trivial interaction should start by retrieving relevant Qdrant/RAG and Markdown/Obsidian context.
- Action selection should explicitly choose among answering, writing a note, calling writer/retriever/indexer agents, generating a skill, or triggering memory compression.
- After execution, extract reusable learning into structured Markdown and inject it into vector retrieval/Qdrant when available.

## Tools

- None recorded.

## Commands

```bash
# None recorded.
```

## Workflow

- Preserve source, extract facts, index for retrieval.

## RAG Notes

- Reusable facts only; avoid transient page noise.
