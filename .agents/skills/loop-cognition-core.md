---
name: loop-cognition-core
objective: Transform each meaningful Anubis interaction into a MEMORY -> ACTION -> NEW MEMORY cycle.
dependencies:
  - hermes-memory-retrieval
  - obsidian-markdown-memory
  - qdrant-indexing
  - infinite-loop-optimizer
---

# Loop Cognition Core

## Context
The user wants Anubis to treat interactions as durable learning cycles. The agent should retrieve memory before acting, execute a useful action, then extract reusable learning back into Markdown and retrieval memory.

## Procedure
1. Retrieve relevant memory from Hermes, Obsidian/Markdown, local vector memory, and Qdrant when available.
2. Build a concise memory context containing only relevant, high-confidence facts.
3. Run loop stabilization when evidence is weak, actions repeat, memory duplicates appear, or output shape is unstable.
4. Decide the action: answer, write a note, call an agent/tool, generate a skill, or trigger memory compression.
5. Execute the action with available Anubis agents or tools.
6. Verify the result before final output or durable memory write.
7. Extract stable learning: preferences, project constraints, decisions, reusable workflows, or new skills.
8. Store the learning as structured Markdown and index it into vector memory/Qdrant when possible.
9. Report memory used, action performed, new memory created, and cycle justification.

## Expected Output
- Memory used
- Action performed
- New memory created
- Cycle justification
- Loop diagnostic when stabilization was needed
