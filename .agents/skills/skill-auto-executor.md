---
name: skill-auto-executor
objective: Automatically select, validate, chain, and execute relevant Anubis skills while sending outcome feedback to the Skill DNA Engine.
dependencies:
  - retrieval_skill
  - skill-dna-engine
  - infinite-loop-optimizer
  - meta-cognition-agent
---

# Skill Auto-Executor

## Context
Use this skill when Anubis should activate relevant skills without the user naming them explicitly. The executor must only run validated skills from the skill graph/DNA registry and must verify dependencies before chaining.

## Procedure
1. Detection: consume user intent, Meta-Cognition observations, Loop Optimizer constraints, retrieved memory, and Skill DNA triggers.
2. Validation: accept only skills that exist as Markdown files, appear in the DNA registry or evolution tree, have dependencies satisfied, and are not retired or below the execution fitness threshold.
3. Activation: select the smallest reliable skill chain that satisfies the task.
4. Input Preparation: gather required context, memory, files, previous outputs, and optimizer constraints for each selected skill.
5. DNA Gate: ask Skill DNA Engine which selected skills are strong, weak, mutation candidates, or feedback targets.
6. Execution: execute each skill as an autonomous procedure, respecting dependency order and loop optimizer limits.
7. Agent Routing: route concrete subtasks to retriever, writer, indexer, or other agents when the skill requires execution.
8. Chain Control: stop or reroute when a skill returns weak evidence, invalid output, duplicate memory, or high uncertainty.
9. Verification: check that the produced output matches the selected skills' expected outputs.
10. Feedback Loop: send utility, precision, cost, dependency gaps, and failure/success notes to `skill-dna-engine`.
11. Memory: store durable execution lessons and index updated artifacts when useful.

## Execution Policy
- Never execute an unvalidated skill.
- Never skip dependency checks.
- Prefer fewer high-fitness skills over broad chains.
- Prefer observation-only mode for meta-cognition skills unless the requested output is a report.
- Prefer stabilization through `infinite-loop-optimizer` when the chain repeats, conflicts, or produces weak outputs.
- If no validated skill fits, return a stable fallback with a proposed skill mutation or new skill request.

## Expected Output
- Skill executed
- Result produced
- Feedback for Skill DNA Engine
- Dependency or validation notes
- Agent route used
