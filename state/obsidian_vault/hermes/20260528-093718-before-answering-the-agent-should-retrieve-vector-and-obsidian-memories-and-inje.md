# Before answering, the agent should retrieve vector and Obsidian memories and inject a merged memory context block into reasoning.

- Created: 2026-05-28T09:37:18.945655+00:00
- Tags: memory-retrieval, qdrant, obsidian, prompt-context, hermes, user-preference, high

## Task
Store pre-answer memory retrieval rule

## Result
For each user query, search vector memory and Obsidian notes, merge relevant results into a memory context block, use it in the response process, and continue normally if no relevant memory exists.

## Lessons
- Retrieve memory before answering.
- Merge vector and Obsidian results into one context block.
- Use retrieved context when relevant; otherwise proceed normally.
