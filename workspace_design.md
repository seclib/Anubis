# ANUBIS Workspace Design

Date: 2026-06-05

## Goal

Design a professional workspace architecture for ANUBIS.

Target layout:

```text
Left:   repository explorer, vault, git
Center: conversation
Bottom: terminal
Right:  execution panel, memory references
```

This is a product and information-architecture design, not an implementation.

## Product Intent

ANUBIS should feel like a focused engineering workspace, not a dashboard-heavy research UI.

Primary user jobs:

- inspect repository context
- ask ANUBIS to plan or perform work
- review execution state
- inspect memory references
- run or observe terminal commands
- understand git changes
- approve, revise, or discard work

Design posture:

```text
quiet, dense, technical, auditable
```

Avoid:

- marketing-style hero layouts
- decorative cards
- large empty panels
- hidden critical state
- oversized agent theatrics

## Layout Overview

```text
┌────────────────────┬──────────────────────────────────────┬──────────────────────┐
│ Left Rail          │ Center Conversation                  │ Right Rail           │
│                    │                                      │                      │
│ Repository         │ Task thread                          │ Execution            │
│ Vault              │ Plan / diff / review messages        │ Memory references    │
│ Git                │ Human approval prompts               │ Risk / status        │
│                    │                                      │                      │
├────────────────────┴──────────────────────────────────────┴──────────────────────┤
│ Bottom Terminal                                                                  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

Recommended default proportions:

```text
Left rail:   260-320 px
Center:      flexible, primary
Right rail:  320-420 px
Terminal:    220-320 px when open
```

Responsive behavior:

- Desktop: three-column layout with bottom terminal.
- Narrow desktop/tablet: right rail collapses into tabs.
- Mobile: not a primary target; use stacked tabs if needed.

## Global Navigation

Top strip:

- workspace/repository name
- current branch
- task status
- model/runtime status
- compact command buttons

Suggested controls:

- `New Task`
- `Plan`
- `Run`
- `Review`
- `Commit`
- `Settings`

Status indicators:

- sandbox mode
- network disabled/enabled
- dirty worktree
- active task
- tests passing/failing

## Left Rail

Purpose:

Show durable workspace context.

Tabs:

```text
Repository | Vault | Git
```

### Repository Explorer

Responsibilities:

- browse files
- show selected task-relevant files
- reveal ranked context files
- show ignored/generated files as hidden by default
- expose file search

Primary views:

1. File tree
2. Ranked context
3. Recent files

File states:

- modified
- added
- deleted
- generated/ignored
- selected for current context
- referenced by memory

Recommended interactions:

- click file to preview in center/right detail mode
- pin file to task context
- exclude file from context
- open diff if modified

Context Builder integration:

```text
Repository Explorer
  -> Ranked Context
     1. core/memory/memory_manager.py
     2. src/anubis/memory.py
     3. tests/test_memory.py
```

### Vault

Purpose:

Expose secret references and restricted memory safely.

Important:

The vault must not show raw secrets. It should show references, metadata, access status, and policy decisions.

Vault item fields:

- provider
- reference
- purpose
- owner
- sensitivity
- last accessed
- access policy

States:

- available
- permission denied
- missing
- expired
- external reference only

Actions:

- copy reference name
- request access
- view audit trail
- attach safe reference to task

Never expose:

- plaintext tokens
- passwords
- private keys
- raw secret values

### Git

Purpose:

Make changes and review state visible.

Views:

1. Status
2. Diff
3. Branches
4. Commit/PR readiness

Git status elements:

- current branch
- upstream status
- changed files
- staged files
- untracked files
- conflicts

Actions:

- stage/unstage
- discard file change
- create branch
- commit
- generate commit message
- open PR draft

Guardrails:

- warn before destructive discard
- preserve user changes
- show ANUBIS-authored vs user-authored changes where possible

## Center Panel: Conversation

Purpose:

The center is the primary work surface.

It should show a task thread, not raw internal graph JSON.

Message types:

- user request
- ANUBIS plan
- context selection
- execution update
- diff summary
- test result
- reviewer decision
- approval prompt

Default thread structure:

```text
User task
Context selected
Plan
Execution progress
Diff / result
Tests
Review
Next actions
```

### Conversation Blocks

#### Task Block

Shows:

- task title
- source
- status
- created time
- current phase

#### Plan Block

Shows:

- steps
- files likely touched
- risks
- required approvals

Actions:

- approve plan
- revise plan
- cancel

#### Context Block

Shows:

- 3-5 selected files
- relevance reasons
- token estimate
- excluded-but-relevant files

Actions:

- add file
- remove file
- rebuild context

#### Diff Block

Shows:

- changed files
- summary
- expandable patch
- risk notes

Actions:

- approve
- request revision
- discard ANUBIS changes

#### Test Block

Shows:

- command
- duration
- pass/fail
- failure summary
- logs link

Actions:

- rerun
- fix failures
- open terminal

#### Review Block

Shows:

- Reviewer decision
- confidence
- risk score
- policy checks
- memory references

Actions:

- accept
- revise
- create commit
- create PR

## Bottom Panel: Terminal

Purpose:

Show command execution and allow controlled developer commands.

Modes:

- ANUBIS command log
- interactive shell
- test runner
- Docker logs

Terminal states:

- idle
- running
- waiting for approval
- failed
- completed

Execution display:

```text
$ PYTHONPATH=src:. python3 scripts/run_tests.py
PASS ...
FAIL ...
```

Guardrails:

- destructive commands require confirmation
- network commands indicate policy state
- command provenance is visible
- commands run in workspace root unless changed

Controls:

- stop command
- rerun
- copy output
- clear terminal
- open full terminal

Terminal should not replace the conversation. It supports evidence.

## Right Rail

Purpose:

Show live operational context.

Tabs:

```text
Execution | Memory
```

### Execution Panel

Responsibilities:

- show active graph/task state
- show Planner/Executor/Reviewer status
- show sandbox decision
- show test/run status
- show risk and approval gates

Recommended sections:

1. Current phase
2. Agent/role status
3. Sandbox
4. Commands
5. Tests
6. Risk

Current phase:

```text
Planning
Context building
Executing
Testing
Reviewing
Waiting for approval
Complete
```

Role status:

```text
Planner   complete
Executor  running
Reviewer  pending
```

Sandbox status:

- filesystem mode
- network mode
- permissions
- denial reason if any

Risk status:

- low/medium/high
- changed files
- protected files touched
- policy findings

### Memory References

Responsibilities:

- show memory records used for the current task
- show repository/vault/conversation references
- expose retrieval reasons
- prevent irrelevant memory from bloating context

Memory categories:

```text
Repository
Conversation
Vault
```

Memory item fields:

- title/source
- namespace
- relevance score
- sensitivity
- why included
- token estimate
- linked file/task/run

Actions:

- pin memory
- exclude memory
- open source
- inspect metadata

Vault memory:

- show reference only
- never show raw secret
- show permission decision

## Workspace State Model

Core state:

```python
WorkspaceState:
    repository: RepositoryState
    active_task: TaskState | None
    context_bundle: ContextBundle | None
    execution: ExecutionState
    terminal: TerminalState
    git: GitState
    memory_refs: tuple[MemoryReference, ...]
```

Task state:

```python
TaskState:
    id: str
    title: str
    status: str
    phase: str
    plan: PlanSummary | None
    selected_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    approvals: tuple[ApprovalGate, ...]
```

## Interaction Model

### New Task Flow

```text
User enters request
  -> Context Builder selects files
  -> Planner shows plan
  -> User approves
  -> Executor runs
  -> Terminal shows commands
  -> Reviewer summarizes
  -> Git panel shows changes
  -> User commits/PRs
```

### Approval Flow

Approval gates:

- before modifying files
- before destructive command
- before network access
- before committing
- before PR creation

Approval prompt location:

- primary in conversation
- status indicator in execution panel
- terminal waits visibly if command is blocked

### Error Flow

When execution fails:

Center:

- failure summary
- suspected cause
- proposed next step

Right:

- failed phase
- command/test status
- sandbox/policy reason

Bottom:

- raw logs

Left:

- changed files remain visible

## Information Density

The workspace should optimize for scanning.

Use:

- compact rows
- monospace file paths
- status chips/icons
- collapsible details
- line-limited summaries

Avoid:

- large cards inside cards
- repeated explanatory prose
- decorative visuals
- oversized headings in tool panels

## Keyboard Shortcuts

Recommended shortcuts:

```text
Cmd/Ctrl+K  command palette
Cmd/Ctrl+Enter send task
Cmd/Ctrl+P  file search
Cmd/Ctrl+`  toggle terminal
Cmd/Ctrl+D  show diff
Cmd/Ctrl+R  rerun last command/test
Esc         close modal/collapse detail
```

## Command Palette

Commands:

- New task
- Rebuild context
- Show plan
- Run tests
- Show diff
- Approve current step
- Reject current step
- Open terminal
- Commit changes
- Create PR
- Toggle memory references
- Toggle vault

## Visual Hierarchy

Priority order:

1. Current task status
2. Required user action
3. Changed files/diff
4. Test result
5. Execution details
6. Memory references
7. Raw logs

Critical information should appear in both:

- center conversation
- right execution panel

## Empty States

Repository:

```text
Open a repository to begin.
```

Conversation:

```text
Ask ANUBIS to inspect, plan, fix, or review this repository.
```

Terminal:

```text
No command has run yet.
```

Execution:

```text
No active task.
```

Memory:

```text
No memory references selected.
```

## Accessibility

Requirements:

- keyboard navigable
- sufficient contrast
- visible focus states
- screen-reader labels for status icons
- do not rely on color alone
- terminal output selectable
- resizable panels

## Performance Requirements

Targets:

| Interaction | Target |
| --- | ---: |
| Open workspace | `<1 s` |
| Switch tabs | `<100 ms` |
| Build context | `<500 ms` local small repo |
| Update execution status | live/streaming |
| Open diff | `<300 ms` |
| Terminal append latency | `<50 ms` |

## Data Flow

```text
Repository service
  -> left repository explorer
  -> context builder

Git service
  -> left git panel
  -> center diff blocks

Task/orchestrator service
  -> center conversation
  -> right execution panel

Terminal service
  -> bottom terminal
  -> execution evidence

Memory service
  -> right memory references
  -> context builder
```

## Mapping to ANUBIS Architecture

| Workspace Surface | ANUBIS Source |
| --- | --- |
| Conversation | graph output, task state, Planner/Executor/Reviewer messages |
| Execution panel | graph state, sandbox decisions, test commands |
| Memory references | unified memory/RAG service |
| Repository explorer | filesystem/context builder |
| Vault | secrets policy and vault memory namespace |
| Git | future git integration |
| Terminal | command execution layer |

## MVP Scope

Build first:

1. Left repository explorer.
2. Center conversation.
3. Bottom terminal.
4. Right execution panel.
5. Git status summary.
6. Memory references list.

Defer:

- full PR workflow
- rich editor
- multi-task dashboard
- custom visual dashboards
- cloud workers

## Final Layout Contract

The professional workspace should always answer:

```text
What task is active?
What context is ANUBIS using?
What is it doing now?
What changed?
What evidence supports the result?
What does the user need to approve?
```

The layout supports that by keeping:

- repository/vault/git on the left
- conversation in the center
- terminal evidence at the bottom
- execution and memory references on the right
