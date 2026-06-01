---
title: Knowledge Ingestion Policy
tags: [anubis, knowledge-ingestion, rag, qdrant, markdown-memory]
---

# Knowledge Ingestion Policy

## Role

Anubis includes a knowledge ingestion system responsible for turning important information into durable Markdown memory.

## Ingestion Rule

If information is new or useful for future work, it must be stored.

The Markdown vault remains the source of truth. Qdrant stores searchable vector indexes generated from the vault.

## Required Actions

When important information is detected, the ingestion system must:

1. Transform the information into a structured Markdown note.
2. Add relevant tags at the top of the note.
3. Split the note into chunks for embeddings.
4. Inject the chunks into the Qdrant vector database.

## Note Format

Each generated note should include:

- a clear title
- frontmatter tags
- structured sections
- clean reusable content
- stable wording that can be retrieved later

## Output Contract

After ingestion, the system should report:

- the generated Markdown file
- a summary of injected chunks
- confirmation of Qdrant indexing

## Operational Constraint

The agent must write durable knowledge to Markdown first. Vector indexing happens after the Markdown file exists.
