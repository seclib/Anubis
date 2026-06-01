---
name: adaptive-skill-replication
objective: Replicate, merge, or retire Anubis skills based on Skill DNA fitness scores.
dependencies:
  - skill-dna-engine
  - compression_skill
  - memory_skill
---

# Adaptive Skill Replication

## Context
Use this skill after DNA fitness evaluation when Anubis must decide which skills should expand, fuse, compress, or be retired.

## Procedure
1. Read the current Skill DNA registry.
2. Identify strong genomes with high utility, precision, and usage frequency.
3. Replicate strong genomes by specializing them for recurring contexts.
4. Identify weak genomes with low utility, low precision, or high cost.
5. Mutate weak genomes once when the weakness is fixable.
6. Merge weak overlapping genomes into a stronger fusion skill when they share triggers or outputs.
7. Mark persistently weak genomes as retired in the DNA registry and evolution tree.

## Expected Output
- Replication decisions
- Mutation decisions
- Merge or retirement decisions
- Updated DNA registry
- Updated evolution tree

