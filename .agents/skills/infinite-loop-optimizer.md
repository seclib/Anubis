---
name: infinite-loop-optimizer
objective: Stabilize Anubis Memory -> Action -> Memory loops by detecting cumulative errors, correcting unstable routes, and optimizing reliable execution paths.
dependencies:
  - loop-cognition-core
  - retrieval_skill
  - memory_skill
  - compression_skill
  - skill-dna-engine
---

# Infinite Loop Optimizer

## Context
Use this skill when an Anubis cognitive loop risks accumulating errors, repeating useless cycles, duplicating memory, or reasoning from weak RAG context. The optimizer must never block the system; it should produce a stable output, reduce cognitive noise, and route toward the safest next action.

## Procedure
1. Diagnose the loop state: current phase, step depth, repeated actions, verification status, memory writes, retrieval confidence, and agent/tool failure patterns.
2. Detect errors:
   - hallucination risk from missing or weak evidence
   - useless infinite loop or repeated tool/action sequence
   - duplicate or low-value memory writes
   - conflicting RAG evidence or stale context
   - invalid agent output shape or empty final result
3. Correct the route:
   - reroute weak knowledge paths to `retrieval_skill` or retriever_agent
   - send duplicate memory to `compression_skill`
   - reset invalid state to the nearest stable phase
   - force verification before final output when uncertainty is high
   - normalize malformed agent outputs into stable expected output
4. Stabilize the loop:
   - respect bounded depth and soft limits
   - avoid recursion unless new evidence or progress exists
   - switch strategy after no-progress cycles
   - balance work between retrieval, action, verification, and memory storage
5. Optimize future cycles:
   - prefer high-fitness skills and high-confidence retrieval
   - reinforce patterns with successful verification
   - merge or retire inefficient paths through Skill DNA selection
   - keep memory concise, deduplicated, and reusable

## Stable Flow
1. Memory retrieval with confidence check.
2. If confidence is weak, reroute to retrieval before action.
3. Action execution with bounded depth and no repeated identical step.
4. Verification before final answer or memory write.
5. Memory eligibility filter.
6. Compression for duplicates or overlapping notes.
7. DNA fitness update for repeated loop patterns.

## Expected Output
- Loop diagnostic
- Corrections applied
- Optimized flow version
- Residual risks or next stabilizing action

