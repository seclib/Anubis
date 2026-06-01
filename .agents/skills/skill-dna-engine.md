---
name: skill-dna-engine
objective: Represent Anubis skills as structured evolvable genomes that can be encoded, mutated, crossed over, evaluated, replicated, merged, or retired.
dependencies:
  - skill-evolution-engine
  - living-cognitive-skill-system
  - memory_skill
  - retrieval_skill
---

# Skill DNA Engine

## Context
Use this skill when Anubis needs to reason about skills as evolvable structures instead of plain Markdown procedures. Each skill receives a genome that can be evaluated and changed over time.

## Skill DNA Schema
```json
{
  "id": "stable-skill-id",
  "name": "human readable skill name",
  "purpose": "why the skill exists",
  "triggers": ["when to activate"],
  "inputs": ["required context or artifacts"],
  "steps": ["ordered agent actions"],
  "outputs": ["expected artifacts or decisions"],
  "dependencies": ["other skill ids"],
  "mutation_rules": ["allowed improvements"],
  "fitness_score": {
    "utility": 0.0,
    "usage_frequency": 0.0,
    "precision": 0.0,
    "cost": 0.0,
    "overall": 0.0
  }
}
```

## Procedure
1. Encoding: parse a skill Markdown file and extract id, name, purpose, triggers, inputs, steps, outputs, dependencies, mutation rules, and initial fitness.
2. Mutation: improve weak genome fields by refining triggers, simplifying steps, correcting dependencies, or narrowing outputs.
3. Crossover: combine two compatible genomes into a hybrid skill when their purposes and outputs reinforce each other.
4. Fitness Evaluation: score utility, usage frequency, precision, and cost from memory, retrieval hits, validation results, and user feedback.
5. Selection: replicate strong skills, merge or compress weak overlapping skills, and retire skills that stay low-value after mutation.
6. Storage: update the Markdown skill, DNA registry, evolution tree, and durable memory.
7. Retrieval: index updated genomes and skill artifacts into vector retrieval/Qdrant when available.

## Mutation Rules
- Improve triggers when a skill is useful but hard to activate.
- Reduce steps when cost is high or repeated execution is slow.
- Add dependencies when a skill repeatedly requires another capability.
- Split a genome when one skill tries to do unrelated jobs.
- Fuse genomes when two skills always appear together.
- Retire or merge skills with low utility and low precision after attempted mutation.

## Expected Output
- Encoded `SKILL_DNA`
- Mutations applied
- Crossover skills generated
- Fitness evaluation
- Registry and evolution tree updates

