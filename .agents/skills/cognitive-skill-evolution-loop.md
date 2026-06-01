---
name: cognitive-skill-evolution-loop
objective: Fuse memory-loop execution with skill evolution so repeated Anubis behavior becomes indexed reusable capability.
dependencies:
  - loop-cognition-core
  - skill-evolution-engine
---

# Cognitive Skill Evolution Loop

## Context
This fusion skill is used when an interaction defines or reveals a reusable agent behavior. It ensures the behavior becomes both memory and an actionable skill.

## Procedure
1. Run the Loop Cognition Core memory phase.
2. Detect whether the interaction contains a repeated or reusable agentic pattern.
3. If useful, create or update a skill Markdown file.
4. If the pattern overlaps existing skills, create a fusion skill or update the evolution tree.
5. Store a concise memory entry summarizing the new capability.
6. Index the skill and memory artifacts into retrieval.
7. Return both cognitive-cycle and skill-evolution outputs.

## Expected Output
- Memory context used
- Action performed
- Skill files created or updated
- Fusion decisions
- Evolution tree changes
- New memory/indexing result

