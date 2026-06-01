---
name: anubis-system-assembly-pipeline
objective: Define the canonical end-to-end Anubis control flow from user input through meta-cognition, stabilization, skill execution, DNA evolution, agents, memory update, and loop restart.
dependencies:
  - meta-cognition-agent
  - infinite-loop-optimizer
  - skill-auto-executor
  - skill-dna-engine
  - retrieval_skill
  - writing_skill
  - memory_skill
---

# Anubis System Assembly Pipeline

## Context
Use this skill as the canonical assembly map for the living Anubis system. It defines how the cognitive layers hand off work without collapsing observation, stabilization, execution, evolution, agents, and memory into one noisy step.

## Procedure
1. User Input: capture the latest user intent and immediate constraints.
2. Meta-Cognition: observe system state, relevant agent patterns, architectural risks, and needed reflective constraints.
3. Loop Optimizer: stabilize the flow by checking recursion risk, weak RAG, duplicate memory, invalid outputs, and no-progress loops.
4. Skill Auto-Executor: select and validate the smallest reliable skill chain.
5. Skill DNA Engine: evaluate selected skill fitness, dependencies, mutation rules, and feedback targets.
6. Agents: route concrete work to retriever, writer, indexer, or other execution agents as needed.
7. Memory Update: store durable learning, update Markdown/RAG, index Qdrant/vector memory, and verify retrieval.
8. Loop Restart: begin the next cycle with updated memory, skill DNA, and system insights.

## Canonical Flow
```text
USER INPUT
-> META-COGNITION
-> LOOP OPTIMIZER
-> SKILL AUTO-EXECUTOR
-> SKILL DNA ENGINE
-> AGENTS (retriever / writer / indexer)
-> MEMORY UPDATE (RAG)
-> LOOP RECOMMENCE
```

## Expected Output
- Active pipeline stage
- Selected skills or agents
- Stabilization decision
- DNA feedback target
- Memory/RAG update result
- Next-loop improvement

