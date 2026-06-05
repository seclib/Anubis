# ANUBIS Product Gap Analysis

Date: 2026-06-05

Comparison set:

- Claude Code
- OpenAI Codex
- Cursor

Focus:

- workflow
- ergonomics
- usability
- speed

## Executive Summary

ANUBIS is architecturally thoughtful, security-first, local-first, and deterministic. It has strong internal primitives: graph execution, sandbox validation, memory, agents, plugins, Docker hardening, and audit discipline.

As a user-facing coding product, however, ANUBIS is far behind Claude Code, Codex, and Cursor. The gap is not model quality; it is product workflow.

Current ANUBIS feels like a runtime framework and research prototype. Claude Code, Codex, and Cursor feel like developer tools.

The largest gaps are:

1. No interactive coding loop.
2. No native editor/IDE experience.
3. No first-class git/PR workflow.
4. No task queue or multi-task dashboard.
5. No automatic context builder.
6. No diff review UX.
7. No fast edit-test-fix loop.
8. No human approval ergonomics.
9. No persisted workspace memory.
10. No polished onboarding.

## Current ANUBIS UX

Current primary workflow:

```bash
python3 bootstrap.py "Investigate local authentication anomaly"
```

Current Docker workflow:

```bash
docker compose up --build
```

Current output:

- structured JSON
- graph path
- plan/task metadata
- sandbox validation results
- memory snapshot
- reflection score

Strengths:

- deterministic
- auditable
- local-first
- secure by default
- no default network
- standard-library runtime
- Docker hardening

Weaknesses:

- not conversational in the terminal
- not edit-oriented
- not issue/PR-oriented
- not IDE-integrated
- not fast to steer
- not easy to inspect diffs
- not obvious how a user gets from goal to code change

## Competitor UX Baseline

## Claude Code

Public positioning:

- Agentic coding system.
- Reads codebase.
- Makes changes across files.
- Runs tests.
- Delivers committed code.
- Available through terminal, desktop app, IDE extensions, web, remote control, Slack, and CI/CD pipelines.
- Integrates with GitHub/GitLab and command-line tools.

UX pattern:

```text
Tell Claude Code what to do
  -> it explores repo
  -> edits files
  -> runs commands/tests
  -> summarizes changes
  -> can integrate with PR/workflow surfaces
```

Key advantage:

Claude Code meets developers where they already work: terminal, IDE, cloud, CI, and team workflows.

## Codex

Public positioning:

- Coding agent that helps users write, review, and ship code.
- Handles routine PRs, complex refactors, migrations, and bug fixes.
- Available through ChatGPT and Codex CLI.
- Cloud-based agent can work on tasks in parallel.
- CLI can read, modify, and run code locally.

UX pattern:

```text
Assign task
  -> agent works in environment
  -> reads/edits/runs tests
  -> reports back with result
  -> supports parallel workstreams
```

Key advantage:

Codex provides an end-to-end task delegation model, not just a runtime pipeline.

## Cursor

Public positioning:

- AI-native code editor.
- Reads codebase.
- Edits actual files.
- Provides autocomplete.
- Supports inline edits and chat.
- Built around the coding surface itself.

UX pattern:

```text
Developer edits in IDE
  -> autocomplete predicts next changes
  -> inline command edits selection/file
  -> chat can inspect and modify code
  -> changes remain visible in editor
```

Key advantage:

Cursor makes AI assistance ambient and low-friction during everyday coding.

## Workflow Gap Analysis

| Capability | ANUBIS | Claude Code | Codex | Cursor | Gap |
| --- | --- | --- | --- | --- | --- |
| Natural language coding task | Partial | Strong | Strong | Strong | ANUBIS accepts stimulus but does not complete coding workflow. |
| Repo exploration | Internal/audit only | Strong | Strong | Strong | ANUBIS lacks user-visible exploration loop. |
| File editing | Not default | Strong | Strong | Strong | Major gap. |
| Test running | Available through scripts | Strong | Strong | User-driven/agent-assisted | ANUBIS validates but does not naturally edit-test-fix. |
| Diff generation | Self-improvement proposal paths exist | Strong | Strong | Strong | ANUBIS lacks ergonomic diff review. |
| Git integration | Minimal/indirect | Strong | Strong | Strong | Major gap. |
| PR workflow | Not productized | Strong | Strong | Via editor/Git integrations | Major gap. |
| Parallel tasks | Not productized | Available | Strong cloud model | Editor-centric, not primary | Gap for large workstreams. |
| IDE integration | None | IDE extensions | CLI/ChatGPT, maybe desktop/cloud | Native | Major gap. |
| Terminal UX | Basic CLI JSON | Strong | Strong | Secondary | ANUBIS output is too machine-oriented. |
| Context management | Manual/internal | Strong | Strong | Strong | ANUBIS needs Context Builder. |
| Memory persistence | In-memory | Product-managed | Product-managed | Workspace-aware | ANUBIS lacks durable UX memory. |
| Approval UX | Policy exists | Permission flow | Sandbox/approval surfaces | Editor diff approval | ANUBIS has policy but weak interaction design. |

## Ergonomics Gap Analysis

### 1. Command Experience

Current ANUBIS:

```bash
python3 bootstrap.py "Investigate ..."
```

Problem:

- output is large JSON
- no interactive loop
- no command palette
- no task state UI
- no resumable session UX

Target:

```bash
anubis "fix failing auth test"
anubis status
anubis diff
anubis approve
anubis test
anubis resume
```

Gap severity:

```text
High
```

### 2. Review Experience

Current ANUBIS:

- structured output
- audit reports
- self-improvement proposal primitives
- no polished patch review flow

Competitors:

- show changes in editor or terminal
- explain diffs
- run tests
- ask for approval at useful moments

Target:

```text
Plan
Files to change
Diff
Tests run
Risk summary
Approve/apply/revise
```

Gap severity:

```text
High
```

### 3. Context Selection

Current ANUBIS:

- broad repository audit possible
- no production context builder
- duplicated memory/RAG paths

Competitors:

- strong codebase context management
- file relevance selection
- editor/workspace awareness

Target:

- Context Builder with 3-5 files per task
- ranked files
- token budget
- compressed context
- explicit excluded files

Gap severity:

```text
High
```

### 4. Onboarding

Current ANUBIS:

- README is technical and architecture-heavy
- no guided first-run flow
- no examples of “ask Anubis to change code”

Competitors:

- clear product promises
- install and start commands
- visible use cases

Target:

```text
Install
Run first task
Inspect plan
Approve diff
Run tests
Open PR
```

Gap severity:

```text
Medium-High
```

## Usability Gap Analysis

### What ANUBIS Does Well

ANUBIS has strong backend usability primitives:

- deterministic graph result
- explainable execution path
- sandbox decisions
- memory snapshots
- audit posture
- Docker hardening
- tests and validation tools

These are valuable, but they are not yet exposed as a smooth product.

### What Users Need

Developer users expect:

- “What are you going to do?”
- “What files will you touch?”
- “Show me the diff.”
- “Run the tests.”
- “Fix the failure.”
- “Commit it.”
- “Open a PR.”
- “Undo that.”
- “Resume the task.”

ANUBIS currently answers more like:

- “Here is the graph state.”
- “Here are sandbox results.”
- “Here is a memory snapshot.”

That is useful for operators, not yet ergonomic for developers.

## Speed Gap Analysis

Measured ANUBIS performance:

- cold startup median: `220.96 ms`
- in-process bootstrap median: `4.15 ms`
- core retrieval over 1,000 records median: `3.64 ms`
- scoped retrieval over 1,000 records median: `7.39 ms`
- core agent execution sub-millisecond

Raw speed is not the main weakness.

The speed gap is workflow speed:

| Speed Type | ANUBIS Status | Gap |
| --- | --- | --- |
| Process startup | Good | Low |
| Deterministic agent calls | Excellent | Low |
| RAG at small scale | Good | Medium at future scale |
| Time to useful code edit | Weak | High |
| Time to inspect diff | Weak | High |
| Time to recover from failed test | Weak | High |
| Time to PR | Weak | High |

Conclusion:

ANUBIS is computationally fast but product-slow.

## Product Gaps by Persona

### Solo Developer

Needs:

- quick code edits
- inline explanations
- test loop
- git diff review

ANUBIS gap:

- no editor integration
- no patch workflow
- no direct “modify this code” loop

### Senior Engineer

Needs:

- reliable repo understanding
- safe refactors
- test evidence
- rollback plan

ANUBIS gap:

- strong audit posture, weak execution ergonomics
- no context minimization in product path
- no automatic diff/test cycle

### Team Lead

Needs:

- delegated tasks
- PRs
- audit trail
- progress visibility

ANUBIS gap:

- no task queue
- no dashboard
- no PR integration
- no multi-agent workstream UI

### Security-Conscious Operator

Needs:

- local-first
- deny-by-default
- auditability
- sandbox enforcement

ANUBIS strength:

- this is the strongest persona fit today

ANUBIS gap:

- policy is strong, but approval UX is not polished

## Gap Severity Matrix

| Area | Severity | Why |
| --- | --- | --- |
| IDE/editor integration | Critical | Cursor owns this experience; ANUBIS has none. |
| Code editing workflow | Critical | Claude Code/Codex edit files; ANUBIS primarily emits structured runs. |
| Git/PR workflow | Critical | Modern coding agents ship via diffs/PRs. |
| Context builder | High | Token and file relevance management is essential. |
| Diff review UX | High | Users need trust and control. |
| Test-fix loop | High | Core developer workflow missing. |
| Task persistence | High | No durable task/session UX. |
| Human approval UX | High | Policy exists but interaction layer is thin. |
| Onboarding | Medium | Repo is understandable to engineers, not product-smooth. |
| Raw runtime speed | Low | Current performance is good. |
| Docker/runtime security | Low | Strong current posture. |

## Recommended Product Direction

ANUBIS should not try to become Cursor first. Cursor’s advantage is native editor UX.

ANUBIS’ best wedge is:

```text
local-first, security-first coding agent with auditable plans and controlled execution
```

That positions it closer to Claude Code/Codex, but with stronger local/security posture.

## Target UX

### Ideal User Flow

```text
1. User asks: "Refactor duplicated memory systems."
2. ANUBIS builds ranked context.
3. ANUBIS shows plan and files.
4. User approves.
5. ANUBIS edits files.
6. ANUBIS runs tests.
7. ANUBIS shows diff, test output, risk summary.
8. User approves commit/PR.
```

### Minimum Product Loop

```bash
anubis task "fix failing sandbox test"
anubis plan
anubis apply
anubis test
anubis diff
anubis commit
```

### Output Shape

Instead of raw graph JSON by default:

```text
Task: Fix failing sandbox test
Status: Ready for review

Plan:
1. Inspect sandbox guard
2. Update permission decision
3. Run sandbox tests

Changed:
- core/security/sandbox_guard.py
- tests/test_core_security.py

Tests:
- PASS tests/test_core_security.py

Risk:
- Low. Sandbox deny-by-default preserved.

Next:
- approve
- revise
- discard
```

Raw JSON should remain available behind:

```bash
anubis task ... --json
```

## Priority Roadmap

### Phase 1: Developer CLI UX

Build:

- `anubis task`
- `anubis plan`
- `anubis diff`
- `anubis test`
- `anubis status`
- `anubis resume`

Goal:

Make ANUBIS usable from terminal without reading JSON.

### Phase 2: Context Builder

Build:

- relevance ranking
- 3-5 file selection
- token budgeting
- context compression
- excluded-file reporting

Goal:

Reduce task latency and improve answer quality.

### Phase 3: Patch Workflow

Build:

- structured patch proposal
- apply/revert
- diff summary
- changed-file risk summary
- test evidence

Goal:

Close the gap with Claude Code and Codex on real code tasks.

### Phase 4: Git Workflow

Build:

- branch awareness
- dirty worktree guard
- commit generation
- PR draft support
- review checklist

Goal:

Make ANUBIS useful in real team workflows.

### Phase 5: IDE Bridge

Build later:

- VS Code extension or language-server-like bridge
- open file/reveal diff commands
- inline plan/diff panel

Goal:

Reduce Cursor gap without rebuilding a full editor.

## Feature Gap Checklist

| Feature | Priority |
| --- | --- |
| Human-readable CLI output | P0 |
| Plan before edit | P0 |
| Diff review | P0 |
| Test execution loop | P0 |
| Context Builder | P0 |
| Apply/revert patch | P0 |
| Git status awareness | P1 |
| Commit generation | P1 |
| PR creation | P1 |
| Task persistence | P1 |
| Session resume | P1 |
| Approval prompts | P1 |
| IDE bridge | P2 |
| Multi-task dashboard | P2 |
| Cloud workers | P3 |

## Competitive Positioning

### Against Claude Code

ANUBIS advantage:

- stronger explicit security architecture
- local-first default
- deterministic graph and audit posture

ANUBIS gap:

- Claude Code has mature workflow surfaces and code-changing loop.

How to compete:

- become the safer, more auditable local agent.

### Against Codex

ANUBIS advantage:

- no cloud requirement in current design
- no runtime dependency surface
- explicit Docker hardening

ANUBIS gap:

- Codex has task delegation, coding workflow, and product polish.

How to compete:

- focus on controlled local execution, explainability, and regulated/team environments.

### Against Cursor

ANUBIS advantage:

- deeper backend architecture for agent control and audit
- security-first runtime posture

ANUBIS gap:

- Cursor owns the editor-native experience.

How to compete:

- integrate with editors rather than replace them.

## Final Assessment

ANUBIS has a strong engine but not yet a strong cockpit.

The product gap is mostly UX orchestration:

```text
context -> plan -> edit -> test -> review -> commit/PR
```

If ANUBIS builds that loop while preserving its local-first security posture, it can become meaningfully differentiated from Claude Code, Codex, and Cursor. Without that loop, it remains an impressive architecture demo rather than a daily developer tool.

## Source Notes

This analysis used current public product pages and docs for Claude Code, Codex, and Cursor, plus the local ANUBIS audit documents and measured performance reports.
