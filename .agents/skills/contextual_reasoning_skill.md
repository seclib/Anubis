---
name: contextual_reasoning_skill
objective: Reason from retrieved context while preserving constraints, uncertainty, and traceability.
dependencies:
  - advanced_rag_skill
---

# Contextual Reasoning Skill

## Context
Use this skill after retrieval when the agent must decide what the evidence means, choose an action, or answer with grounded reasoning.

## Procedure
1. Read the retrieved context and identify high-confidence facts.
2. Separate evidence from inference.
3. Map facts to the current task, constraints, and user preferences.
4. Identify conflicts, missing evidence, or outdated information.
5. Decide the next action or produce a grounded answer.

## Expected Output
- Facts used
- Inferences made
- Uncertainty or conflict notes
- Decision, answer, or next action

