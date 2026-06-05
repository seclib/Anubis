# ANUBIS Agent Simplification

Date: 2026-06-05

## Goal

Simplify all ANUBIS agent systems into three canonical roles:

```text
Planner
Executor
Reviewer
```

This document is analysis and architecture guidance only. No implementation is included.

## Current Agent Systems

ANUBIS currently has three overlapping agent families plus swarm coordination layers.

### 1. Core Graph Agents

Location:

```text
core/agents/
```

Agents:

- `PlannerAgent`
- `AnalystAgent`
- `ExecutorAgent`
- `CriticAgent`

Used by:

- `core.graph`
- `core.execution.sandbox_runner`
- `core.swarm`

Current graph flow:

```text
planner -> analyst -> executor -> critic
```

### 2. Living Runtime Agents

Location:

```text
src/anubis/agents_life/
```

Agents:

- `WatcherAgent`
- `ThinkerAgent`
- `ExecutorAgent`
- `HealerAgent`
- `PredatorAgent`

Used by:

- `src/anubis/life_cycle/boot_sequence.py`
- `src/anubis/core_life/living_loop.py`
- async living-runtime orchestrator

Current living-loop intent:

```text
watch -> think -> execute -> heal/defend
```

### 3. Research Swarm Agents

Location:

```text
agents/
src/anubis/core_life/swarm/
```

Agents:

- `research_planner`
- `research_executor`
- `research_analyst`
- `research_critic`
- `research_synthesizer`

Used by:

- `HiveMind`
- research swarm tests

Current research flow:

```text
planner -> executor -> analyst + critic -> synthesizer -> consensus
```

### 4. Swarm Coordination Layers

Locations:

```text
core/swarm/
src/anubis/swarm.py
src/anubis/core_life/swarm/
```

Responsibilities:

- role assignment
- agent scoring
- dynamic replacement
- voting
- consensus
- confidence weighting
- multi-agent reasoning chains

These layers duplicate some Reviewer responsibilities by adding second-order reasoning over already-structured agent outputs.

## Redundant Agents

| Agent | Current Role | Redundancy | Target Classification |
| --- | --- | --- | --- |
| `core.agents.PlannerAgent` | Converts objective into task graph | Canonical planning role already exists | `Planner` |
| `agents.PlannerAgent` | Research planning | Overlaps with core planner | Merge into `Planner` as research mode |
| `src/anubis/agents_life/ThinkerAgent` | Reasoning, triage, hypothesis | Overlaps Planner and Analyst | Merge into `Planner` |
| `core.agents.AnalystAgent` | Interprets observations | Overlaps Thinker, Watcher, research Analyst | Merge into `Reviewer` or Planner evidence-analysis helper |
| `agents.AnalystAgent` | Research interpretation | Overlaps core Analyst | Merge into `Reviewer` |
| `src/anubis/agents_life/WatcherAgent` | Collects synthetic telemetry/context | Not a reasoning agent; it is a tool-like context collector | Fold into `Executor` as observe/collect action |
| `core.agents.ExecutorAgent` | Prepares sandbox request | Canonical execution role exists | `Executor` |
| `src/anubis/agents_life/ExecutorAgent` | Recommends defensive response | Overlaps Executor but currently advisory | Merge into `Executor` as safe action/recommendation mode |
| `agents.ResearchExecutorAgent` | Research action simulation | Overlaps Executor | Merge into `Executor` as research mode |
| `core.agents.CriticAgent` | Reviews output risk/completeness | Canonical review role exists | `Reviewer` |
| `agents.CriticAgent` | Research critique | Overlaps core Critic | Merge into `Reviewer` |
| `agents.SynthesizerAgent` | Final research answer synthesis | Overlaps Reviewer final assessment | Merge into `Reviewer` |
| `src/anubis/agents_life/HealerAgent` | Recovery guidance | Not a distinct reasoning role | Fold into `Executor` as recovery action mode |
| `src/anubis/agents_life/PredatorAgent` | Defense/kill-switch posture | Overlaps safety monitor and Reviewer risk decision | Fold into `Reviewer` for risk decision, `Executor` for defensive action |

## Overlapping Responsibilities

### Planning and Reasoning

Current overlaps:

- `core PlannerAgent`
- `research PlannerAgent`
- `ThinkerAgent`
- `src/anubis/planner.py`
- `core/planner`
- `cognitive_loop`
- `task_digestion`

Problem:

ANUBIS has multiple places that convert stimulus into intent, plan, task graph, reasoning trace, or strategy. This creates duplicated reasoning layers before execution.

Target:

`Planner` owns:

- intent normalization
- task decomposition
- dependency ordering
- strategy selection
- selection of required tools/capabilities
- producing an execution plan

### Analysis and Review

Current overlaps:

- `core AnalystAgent`
- `research AnalystAgent`
- `ThinkerAgent`
- `CriticAgent`
- `research CriticAgent`
- `SynthesizerAgent`
- swarm consensus
- reflection node

Problem:

Analysis, critique, synthesis, and consensus are spread across many agents. The same run may be interpreted, criticized, reflected, voted on, and synthesized by separate layers.

Target:

`Reviewer` owns:

- evidence analysis
- output critique
- risk scoring
- policy validation
- confidence scoring
- final synthesis
- accept/revise/reject decision

### Execution

Current overlaps:

- `core ExecutorAgent`
- living `ExecutorAgent`
- `ResearchExecutorAgent`
- `WatcherAgent`
- `HealerAgent`
- parts of `PredatorAgent`
- execution layer
- sandbox runner

Problem:

Some agents prepare sandbox requests, some simulate research execution, some recommend response, some collect context, and some recover. These are all execution modes, not independent agent identities.

Target:

`Executor` owns:

- context collection
- sandbox request preparation
- safe local execution
- recovery action preparation
- defensive action preparation
- tool/plugin invocation through sandbox
- returning structured execution evidence

## Duplicated Reasoning Layers

| Layer | Current Location | Duplicate With | Target |
| --- | --- | --- | --- |
| Intent inference | `IntentInference`, `InputNode`, `PlannerAgent` | Planner task decomposition | `Planner` |
| Task digestion | `TaskDigestion`, `core/planner`, `src/anubis/planner.py` | Planner templates | `Planner` |
| Evidence interpretation | `AnalystAgent`, `ThinkerAgent`, research Analyst | Critic/reviewer analysis | `Reviewer` |
| Critique | `CriticAgent`, research Critic | Reflection and consensus | `Reviewer` |
| Synthesis | `SynthesizerAgent`, `OutputNode`, reflection | Reviewer final decision | `Reviewer` plus graph output formatter |
| Consensus | `core/swarm`, `src/anubis/swarm`, `HiveMind` | Reviewer confidence and acceptance | `Reviewer` |
| Agent scoring/replacement | `AgentPool`, `ResearchAgentRegistry`, `SwarmCoordinator` | Runtime scheduling concern | Orchestrator, not agent role |
| Recovery reasoning | `HealerAgent` | Executor action mode and Reviewer risk decision | `Executor` + `Reviewer` |
| Defensive suppression | `PredatorAgent`, `SafetyMonitor`, kill switch | Reviewer risk + security kernel | `Reviewer` + security system |

## Target Architecture

### Canonical Roles

```text
Planner -> Executor -> Reviewer
```

### Planner

Purpose:

Transform stimulus into a deterministic, auditable execution plan.

Owns:

- intent inference
- goal normalization
- task graph creation
- dependency ordering
- required capabilities
- execution constraints
- expected evidence

Does not own:

- execution
- policy approval
- final acceptance

### Executor

Purpose:

Perform or prepare allowed work through sandboxed boundaries and return evidence.

Owns:

- context collection
- sandbox request construction
- safe tool/plugin invocation
- retry/timeout execution envelope
- recovery action preparation
- defensive response preparation
- structured evidence output

Does not own:

- deciding whether the plan is good
- final risk acceptance
- policy override

### Reviewer

Purpose:

Evaluate planner and executor outputs for correctness, safety, confidence, and completeness.

Owns:

- evidence interpretation
- risk scoring
- policy checks
- critique
- synthesis
- confidence score
- accept/revise/reject decision
- final review notes

Does not own:

- mutating execution state
- dispatching tools directly
- creating hidden follow-up plans

## Mapping Current Agents to Target Roles

| Current Agent/System | Target Role | Migration Notes |
| --- | --- | --- |
| `core PlannerAgent` | `Planner` | Keep as initial canonical implementation. |
| `research PlannerAgent` | `Planner` | Convert to Planner research mode or remove after feature parity. |
| `ThinkerAgent` | `Planner` | Preserve hypothesis generation as Planner reasoning metadata. |
| `core ExecutorAgent` | `Executor` | Keep sandbox request behavior. |
| living `ExecutorAgent` | `Executor` | Preserve defensive recommendation mode. |
| `ResearchExecutorAgent` | `Executor` | Preserve research execution as non-networked evidence collection mode. |
| `WatcherAgent` | `Executor` | Convert to context collection capability. |
| `HealerAgent` | `Executor` | Convert to recovery action capability. |
| `PredatorAgent` | `Reviewer` + `Executor` | Reviewer decides risk/kill-switch recommendation; Executor prepares defensive action. |
| `core AnalystAgent` | `Reviewer` | Fold evidence interpretation into Reviewer. |
| `research AnalystAgent` | `Reviewer` | Fold into Reviewer research mode. |
| `core CriticAgent` | `Reviewer` | Keep as initial canonical review implementation. |
| `research CriticAgent` | `Reviewer` | Fold into Reviewer research mode. |
| `SynthesizerAgent` | `Reviewer` | Fold final synthesis into Reviewer. |
| `ReflectionNode` | `Reviewer` or graph metric node | Keep deterministic metrics, but avoid separate reasoning identity. |
| `HiveMind` | Orchestration pattern | Replace multi-agent consensus with Reviewer decision path. |
| `core/swarm` | Optional orchestration strategy | Do not model as separate agents. |

## Proposed Runtime Flow

### Graph Runtime

Current:

```text
input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output
```

Target:

```text
input -> planner -> executor -> reviewer -> memory -> output
```

Notes:

- `agent_dispatch` becomes simple role dispatch, not multi-agent swarm routing.
- `execution_sandbox` becomes part of `Executor`.
- `reflection` becomes part of `Reviewer` or a non-agent metrics step.

### Living Runtime

Current:

```text
watcher + thinker + executor + healer + predator
```

Target:

```text
Planner(reason/triage)
Executor(observe/execute/recover/defend)
Reviewer(policy/risk/final decision)
```

### Research Runtime

Current:

```text
planner -> executor -> analyst + critic -> synthesizer -> consensus
```

Target:

```text
Planner(research plan)
Executor(collect evidence)
Reviewer(analyze + critique + synthesize + decide)
```

## What to Keep

Keep these behaviors, not necessarily these classes:

- deterministic task planning
- structured agent result envelopes
- sandbox-only execution preparation
- context collection
- recovery recommendations
- defensive risk checks
- evidence interpretation
- critique and risk scoring
- research synthesis
- confidence scoring
- traceable explanations
- memory writes for agent outputs
- tests that prove safety and determinism

## What to Remove or Deprecate

Deprecate as standalone agent identities:

- `AnalystAgent`
- `CriticAgent`
- `SynthesizerAgent`
- `WatcherAgent`
- `ThinkerAgent`
- `HealerAgent`
- `PredatorAgent`
- research-specific role classes once mapped into modes

Remove eventually:

- multi-agent consensus as a required reasoning layer
- separate research role allocator
- duplicate agent descriptor classes
- duplicate agent registries
- duplicate agent scoring systems

Keep temporarily:

- import-path compatibility adapters
- existing class names as wrappers around Planner/Executor/Reviewer
- research hive tests until equivalent target-flow tests exist

## Shared Agent API

All target agents should implement one contract:

```python
AgentRequest:
    run_id: str
    role: "planner" | "executor" | "reviewer"
    objective: str
    input: dict
    context: dict
    constraints: dict

AgentResponse:
    ok: bool
    role: str
    action: str
    output: dict
    evidence: tuple[str, ...]
    confidence: float
    risk_score: float | None
    decision: "accept" | "revise" | "reject" | None
    explanation: tuple[str, ...]
    trace: tuple[str, ...]
```

## Migration Plan

### Phase 1: Freeze Current Behavior

1. Capture current outputs for graph, living loop, and research swarm tests.
2. Define canonical Planner/Executor/Reviewer contract.
3. Add adapters that let old agent classes emit the new response shape.

Risk: Low.

### Phase 2: Introduce Target Agents

1. Create `Planner` backed by current `core PlannerAgent` and planner engine.
2. Create `Executor` backed by current sandbox executor behavior.
3. Create `Reviewer` backed by current critic behavior plus analyst/synthesizer behavior.
4. Keep old agents as wrappers.

Risk: Medium.

### Phase 3: Collapse Graph Agent Dispatch

1. Replace role mapping with fixed Planner/Executor/Reviewer dispatch.
2. Move `analysis.*` and `policy.*` task handling into Reviewer.
3. Move sandbox request generation into Executor.
4. Keep graph node names stable until tests are updated.

Risk: Medium.

### Phase 4: Collapse Living Agents

1. Map watcher output to Executor context collection.
2. Map thinker output to Planner reasoning metadata.
3. Map healer output to Executor recovery mode.
4. Map predator output to Reviewer risk decision and Executor defensive action.
5. Keep old living agent wrappers until living-loop tests pass.

Risk: Medium to High.

### Phase 5: Collapse Research Swarm

1. Map research planner to Planner research mode.
2. Map research executor to Executor research mode.
3. Map analyst, critic, and synthesizer to Reviewer research mode.
4. Replace weighted swarm consensus with Reviewer confidence and decision.
5. Preserve reasoning chain as Reviewer substeps rather than separate agent votes.

Risk: High, because research tests currently expect five role outputs.

### Phase 6: Remove Redundant Systems

Only after compatibility tests pass:

1. Remove duplicate agent registries.
2. Remove duplicate descriptor classes.
3. Remove standalone agent classes that only wrap target roles.
4. Remove mandatory swarm consensus from core flow.
5. Update `config/agents.yaml` to list only:

```yaml
runtime_agents:
  - planner
  - executor
  - reviewer
research_agents:
  - planner
  - executor
  - reviewer
```

Risk: Medium.

## Compatibility Strategy

Temporary wrappers:

```text
AnalystAgent -> Reviewer(mode="analysis")
CriticAgent -> Reviewer(mode="critique")
SynthesizerAgent -> Reviewer(mode="synthesis")
WatcherAgent -> Executor(mode="observe")
ThinkerAgent -> Planner(mode="reason")
HealerAgent -> Executor(mode="recover")
PredatorAgent -> Reviewer(mode="risk") + Executor(mode="defend")
ResearchExecutorAgent -> Executor(mode="research")
```

This allows old imports and tests to survive while internal logic moves to the target architecture.

## Reviewer as Consensus Replacement

The current research swarm uses five agents and weighted consensus. In the simplified architecture, Reviewer replaces consensus by producing:

- evidence summary
- critique
- synthesis
- confidence
- decision
- conflicts
- revision request when needed

Equivalent output:

```python
ReviewerOutput:
    decision: "accept" | "revise" | "reject"
    confidence: float
    evidence: tuple[str, ...]
    issues: tuple[dict, ...]
    conflicts: tuple[str, ...]
    synthesis: str
```

This preserves the value of consensus without maintaining separate Analyst, Critic, and Synthesizer agents.

## Risks

| Risk | Level | Mitigation |
| --- | --- | --- |
| Research tests expect five agents | High | Add compatibility wrappers and migrate tests last. |
| Living loop depends on capability-based agent selection | Medium | Map capabilities to Executor/Planner/Reviewer modes. |
| Reviewer becomes too large | Medium | Keep Reviewer internally modular, but expose one agent role. |
| Loss of traceability | Medium | Preserve substep trace entries inside each target agent response. |
| Safety regression | High | Keep sandbox and security decisions outside agent discretion. |
| Over-collapse of useful separation | Medium | Collapse public roles, not internal helper classes. |

## Verification Gates

Before removing any old agent class:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 scripts/run_tests.py
python3 bootstrap.py "Investigate simplified agent regression" --source agent-simplification
PYTHONPATH=src:. python3 tools/sandbox_tester.py
```

Required preserved behavior:

- graph bootstrap succeeds
- sandbox request preparation remains executor-owned
- reviewer flags unsafe or empty outputs
- research flow still produces traceable reasoning
- living loop still writes memory and emits events
- no generated code execution
- no direct OS execution

## Final Target

The simplified ANUBIS agent architecture should present only three agent identities:

```text
Planner
Executor
Reviewer
```

Internal modes may remain, but they should not appear as independent agents unless there is a strong operational reason. This reduces agent proliferation, duplicated reasoning, and consensus overhead while preserving the current system’s core behaviors.
