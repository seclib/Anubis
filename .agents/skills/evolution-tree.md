# Anubis Skill Evolution Tree

## Nodes
- `loop-cognition-core`: converts interactions into MEMORY -> ACTION -> NEW MEMORY cycles.
- `skill-evolution-engine`: creates, merges, and evolves reusable agentic skills.
- `cognitive-skill-evolution-loop`: fused skill that turns repeated cognitive behavior into indexed reusable skills.

## Evolution Edges
- `loop-cognition-core -> cognitive-skill-evolution-loop`
- `skill-evolution-engine -> cognitive-skill-evolution-loop`

## Fusion Edges
- `loop-cognition-core + skill-evolution-engine -> cognitive-skill-evolution-loop`

## Maintenance Rules
- Add an evolution edge when a skill supersedes or specializes an older skill.
- Add a fusion edge when two or more skills are deliberately combined.
- Prefer concise, actionable skills over abstract taxonomies.
- Update this tree whenever a skill is created, merged, renamed, or deprecated.

