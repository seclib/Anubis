# Anubis Skill Evolution Tree

## Nodes
- `loop-cognition-core`: converts interactions into MEMORY -> ACTION -> NEW MEMORY cycles.
- `skill-evolution-engine`: creates, merges, and evolves reusable agentic skills.
- `skill-dna-engine`: encodes skills as evolvable genomes with mutation, crossover, fitness, replication, merge, and retirement rules.
- `cognitive-skill-evolution-loop`: fused skill that turns repeated cognitive behavior into indexed reusable skills.
- `living-cognitive-skill-system`: meta-skill that makes cognition, useful action detection, skill evolution, memory storage, and retrieval reinforcement operate as one self-improving loop.
- `adaptive-skill-replication`: applies DNA selection pressure by replicating strong skills and mutating, merging, or retiring weak skills.
- `infinite-loop-optimizer`: stabilizes Memory -> Action -> Memory loops by detecting hallucination risk, useless recursion, duplicate memory, RAG incoherence, and invalid outputs.
- `meta-cognition-agent`: observes retriever, writer, indexer, skill engine, and loop optimizer behavior without direct execution, producing system-level cognition reports and restructuring suggestions.
- `skill-auto-executor`: automatically selects, validates, chains, and executes relevant skills while feeding outcomes back to Skill DNA.
- `anubis-system-assembly-pipeline`: canonical end-to-end pipeline from user input through meta-cognition, stabilization, skill execution, DNA evolution, agents, memory update, and loop restart.
- `retrieval_skill`: retrieves relevant knowledge from memory, notes, vectors, and Qdrant.
- `advanced_rag_skill`: extends retrieval with query planning, hybrid search, filters, and confidence checks.
- `contextual_reasoning_skill`: reasons from retrieved context while preserving uncertainty and traceability.
- `writing_skill`: produces reusable written artifacts.
- `structured_note_skill`: creates retrieval-friendly Markdown notes.
- `documentation_skill`: turns implementation knowledge into maintainable documentation.
- `memory_skill`: stores durable learning into Anubis memory.
- `compression_skill`: compresses overlapping memories into canonical reusable principles.
- `summarization_skill`: summarizes interactions, evidence, and outcomes into compact knowledge.
- `knowledge_synthesis_skill`: fuses retrieval and writing into durable knowledge synthesis.

## Evolution Edges
- `loop-cognition-core -> cognitive-skill-evolution-loop`
- `skill-evolution-engine -> cognitive-skill-evolution-loop`
- `skill-evolution-engine -> skill-dna-engine -> adaptive-skill-replication`
- `cognitive-skill-evolution-loop -> living-cognitive-skill-system`
- `loop-cognition-core -> infinite-loop-optimizer -> living-cognitive-skill-system`
- `infinite-loop-optimizer -> meta-cognition-agent -> skill-dna-engine`
- `skill-dna-engine -> skill-auto-executor -> living-cognitive-skill-system`
- `meta-cognition-agent -> infinite-loop-optimizer -> skill-auto-executor -> skill-dna-engine -> living-cognitive-skill-system`
- `retrieval_skill -> advanced_rag_skill -> contextual_reasoning_skill`
- `writing_skill -> structured_note_skill`
- `writing_skill -> documentation_skill`
- `memory_skill -> compression_skill`
- `memory_skill -> summarization_skill`

## Fusion Edges
- `loop-cognition-core + skill-evolution-engine -> cognitive-skill-evolution-loop`
- `retrieval_skill + writing_skill -> knowledge_synthesis_skill`
- `loop-cognition-core + skill-evolution-engine + memory_skill + retrieval_skill -> living-cognitive-skill-system`
- `skill-dna-engine + compression_skill + memory_skill -> adaptive-skill-replication`
- `loop-cognition-core + retrieval_skill + memory_skill + compression_skill -> infinite-loop-optimizer`
- `retrieval_skill + writing_skill + skill-evolution-engine + infinite-loop-optimizer -> meta-cognition-agent`
- `retrieval_skill + skill-dna-engine + infinite-loop-optimizer + meta-cognition-agent -> skill-auto-executor`
- `meta-cognition-agent + infinite-loop-optimizer + skill-auto-executor + skill-dna-engine + memory_skill -> anubis-system-assembly-pipeline`

## Skill Root
- `retrieval_skill`
  - `advanced_rag_skill`
    - `contextual_reasoning_skill`
- `writing_skill`
  - `structured_note_skill`
  - `documentation_skill`
- `memory_skill`
  - `compression_skill`
  - `summarization_skill`
- Fusion examples
  - `retrieval_skill + writing_skill -> knowledge_synthesis_skill`
  - `loop-cognition-core + skill-evolution-engine + memory_skill + retrieval_skill -> living-cognitive-skill-system`
  - `skill-dna-engine + compression_skill + memory_skill -> adaptive-skill-replication`
  - `loop-cognition-core + retrieval_skill + memory_skill + compression_skill -> infinite-loop-optimizer`
  - `retrieval_skill + writing_skill + skill-evolution-engine + infinite-loop-optimizer -> meta-cognition-agent`
  - `retrieval_skill + skill-dna-engine + infinite-loop-optimizer + meta-cognition-agent -> skill-auto-executor`
  - `meta-cognition-agent + infinite-loop-optimizer + skill-auto-executor + skill-dna-engine + memory_skill -> anubis-system-assembly-pipeline`

## Canonical Assembly Pipeline
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

## Skill DNA Layer
- `skill-dna-engine`
  - encodes Markdown skills as structured genomes
  - mutates steps, triggers, dependencies, and outputs
  - crosses over compatible genomes into hybrids
  - evaluates utility, usage frequency, precision, and cost
- `adaptive-skill-replication`
  - replicates strong high-fitness skills
  - mutates weak but promising skills
  - merges or retires persistently weak skills

## Living System Loop
- `loop-cognition-core`
  - retrieves memory
  - executes useful action
  - extracts learning
- `infinite-loop-optimizer`
  - detects unstable recursion, weak RAG, duplicate memory, and invalid output
  - reroutes to retrieval, compression, verification, or stable state reset
  - prefers reliable paths and suppresses cognitive noise
- `meta-cognition-agent`
  - observes agent decisions and patterns without executing their workflows
  - identifies inefficiencies, repeated errors, redundancy, and memory-flow problems
  - proposes architecture changes and Skill DNA mutations
- `skill-auto-executor`
  - selects validated skills from context and DNA triggers
  - verifies dependencies before activation
  - executes the smallest reliable skill chain
  - returns feedback to Skill DNA fitness evaluation
- `skill-evolution-engine`
  - observes repeated or useful patterns
  - creates, improves, fuses, or compresses skills
- `memory_skill`
  - stores the skill and learning as durable Markdown memory
- `retrieval_skill`
  - indexes and retrieves the improved capability
- `living-cognitive-skill-system`
  - restarts the loop with better capacity

## Maintenance Rules
- Add an evolution edge when a skill supersedes or specializes an older skill.
- Add a fusion edge when two or more skills are deliberately combined.
- Prefer concise, actionable skills over abstract taxonomies.
- Update this tree whenever a skill is created, merged, renamed, or deprecated.
