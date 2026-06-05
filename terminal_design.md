# ANUBIS Integrated Terminal Architecture

Date: 2026-06-05

## Goal

Design an integrated terminal architecture for ANUBIS.

Requirements:

- streaming output
- sandbox awareness
- execution logs
- command history

This is a design artifact only. It does not modify runtime behavior.

## Product Intent

The terminal should make execution visible, controllable, and auditable.

It should support the professional workspace layout:

```text
Center: conversation and review
Bottom: integrated terminal
Right: execution state and memory references
```

The terminal is not the primary agent interface. It is the evidence surface for commands, tests, build steps, Docker operations, Git commands, and sandbox decisions.

## Current Repository Context

ANUBIS currently has strong safety posture but limited real process execution in the active graph path.

Relevant observations from prior audits:

- Active graph path: `input -> planner -> agent_dispatch -> execution_sandbox -> memory -> reflection -> output`.
- Current graph sandbox validates structured execution requests.
- Active graph execution does not spawn arbitrary OS processes.
- Docker hardening provides whole-app isolation, not per-command isolation.
- Duplicate execution/sandbox concepts exist under `core/` and `src/anubis/`.
- Product gap analysis identified terminal UX as too machine-oriented.

Design implication:

The terminal architecture must distinguish between:

```text
displaying execution evidence
running user-approved commands
running sandboxed agent commands
```

Those are separate modes with different policy requirements.

## Terminal Roles

The integrated terminal has four roles:

1. Live command output
2. Execution evidence log
3. Interactive developer shell
4. Sandbox/policy visibility surface

It should answer:

- what command is running?
- who initiated it?
- where is it running?
- what sandbox policy applies?
- what output has streamed so far?
- did it succeed, fail, time out, or get denied?
- how can the user rerun or inspect it?

## Layout

The terminal lives in the bottom panel.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Left Rail        │ Center Conversation                  │ Right Rail     │
│                  │                                      │                │
├──────────────────┴──────────────────────────────────────┴────────────────┤
│ Terminal tabs: Task Log | Shell | Tests | Git | Docker                    │
│ $ PYTHONPATH=src:. python3 scripts/run_tests.py                           │
│ PASS test_core_plugins.py                                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

Default height:

```text
collapsed: 36 px
open:      240-320 px
expanded: 50-70% viewport height
```

Terminal tabs:

- Task Log
- Shell
- Tests
- Git
- Docker
- System

The Task Log tab should be default during agent execution.

## Terminal Modes

### Task Log Mode

Purpose:

Show commands and structured execution events initiated by ANUBIS.

Examples:

- context scan
- test run
- git diff
- Docker image inspection
- dependency audit command
- sandbox validation result

User capabilities:

- pause autoscroll
- copy output
- jump to failure
- rerun command
- open full command details

### Shell Mode

Purpose:

Allow the user to run manual commands in the workspace.

Shell mode should be explicit. It should not be confused with ANUBIS-controlled execution.

User capabilities:

- type commands
- use command history
- interrupt command
- change directory within allowed workspace
- copy/paste

Guardrails:

- show workspace root
- show sandbox/network state
- warn on destructive commands
- record commands in audit log when configured

### Test Mode

Purpose:

Group test/build commands and their results.

Examples:

```bash
PYTHONPATH=src:. python3 scripts/run_tests.py
PYTHONPATH=src:. python3 tools/sandbox_tester.py
python3 -m compileall core src tests
```

Features:

- pass/fail summary
- duration
- failure grouping
- rerun failed command
- attach result to task review

### Git Mode

Purpose:

Show Git commands and output related to branch, diff, commit, and PR workflows.

Examples:

```bash
git status --short
git diff --stat
git diff --cached
git log --oneline -n 20
```

Git mode should integrate with `git_experience_design.md`.

### Docker Mode

Purpose:

Show Docker build, image, and runtime logs.

Examples:

```bash
docker build -t anubis:local .
docker image inspect anubis:local
docker compose config
```

Docker commands may require elevated risk labels because they can consume disk, network, CPU, and host daemon resources.

### System Mode

Purpose:

Show environment and diagnostics.

Examples:

```bash
python3 --version
git --version
docker --version
env
```

Sensitive environment values should be redacted by default.

## Architecture Overview

```text
Terminal UI
  -> Terminal Session Manager
     -> Command Router
        -> Sandbox Policy Evaluator
        -> Execution Adapter
           -> Local Process Adapter
           -> Docker Adapter
           -> Git Adapter
           -> Test Adapter
        -> Stream Multiplexer
        -> Execution Log Store
        -> Command History Store
```

## Core Components

### Terminal UI

Responsibilities:

- render terminal output
- render command status
- render sandbox indicators
- accept manual input
- support copy/search/history
- show command metadata without cluttering output

Terminal chrome should show:

- active tab
- current working directory
- sandbox mode
- network mode
- command status
- elapsed time
- exit code

Example:

```text
Tests | /home/fatsio/AI/Anubis | sandbox: workspace | network: off | running 00:13
```

### Terminal Session Manager

Responsibilities:

- create terminal sessions
- restore terminal sessions
- track active process
- manage terminal tabs
- enforce one foreground interactive process per tab
- expose historical completed commands

Session fields:

```text
TerminalSession
  id
  tab
  mode
  cwd
  shell
  sandbox_profile
  network_policy
  active_command_id
  created_at
  updated_at
```

### Command Router

Responsibilities:

- normalize command requests
- classify command intent
- select execution adapter
- apply policy checks
- route output streams
- record command lifecycle events

Command origins:

```text
UserShell
AgentTask
TestRunner
GitWorkflow
DockerWorkflow
SystemDiagnostic
```

Origin matters because approval and logging rules differ.

### Sandbox Policy Evaluator

Responsibilities:

- classify command risk
- apply sandbox policy
- determine approval requirement
- explain denied commands
- attach policy decision to execution log

Policy dimensions:

- filesystem access
- network access
- process spawning
- source modification
- secret access
- Docker daemon access
- Git mutation
- destructive file operations

Possible decisions:

```text
Allow
AllowWithWarning
RequireApproval
Deny
```

### Execution Adapter

Responsibilities:

- start process or operation
- stream stdout/stderr
- handle cancellation
- enforce timeout
- capture exit code
- produce normalized execution result

Adapters:

- Local Process Adapter
- Docker Adapter
- Git Adapter
- Test Adapter
- Read-only Diagnostic Adapter

### Stream Multiplexer

Responsibilities:

- merge stdout, stderr, and structured events
- preserve ordering
- keep stream chunks small
- support backpressure
- support paused autoscroll
- allow late subscribers to replay buffered output

Stream event types:

```text
stdout
stderr
status
policy
metadata
error
summary
```

### Execution Log Store

Responsibilities:

- store command lifecycle
- store redacted output chunks
- store sandbox decisions
- store timing and exit metadata
- link commands to tasks, commits, PRs, and reviews

The execution log is the durable audit trail.

### Command History Store

Responsibilities:

- store user-entered commands
- store ANUBIS-suggested commands
- support search
- support rerun
- avoid storing secret-bearing commands when detected
- distinguish manual vs agent-originated commands

## Streaming Output

### Output Requirements

Streaming output should:

- appear within 50 ms of receiving a chunk
- preserve stdout/stderr ordering as closely as possible
- support long-running commands
- avoid freezing the UI on large output
- remain searchable after completion
- expose raw output and summarized output

### Stream Lifecycle

```text
Queued
PolicyEvaluating
WaitingForApproval
Starting
Running
Cancelling
Completed
Failed
TimedOut
Denied
```

### Stream Event Shape

```text
TerminalStreamEvent
  command_id
  sequence
  stream
  payload
  redacted
  timestamp
```

`stream` values:

```text
stdout
stderr
system
policy
summary
```

### Chunking

Recommended chunking:

- flush on newline
- flush after 50 ms
- cap chunk size around 4-16 KB
- mark truncated chunks explicitly

For very large output:

- keep visible ring buffer
- persist full redacted log separately
- collapse repeated lines
- show jump points for errors

### Backpressure

If output is faster than UI rendering:

- continue capturing log
- pause visual rendering
- show skipped live-render count
- allow user to jump to latest

Example:

```text
Rendering paused: 12,480 lines captured. Jump to latest.
```

## Sandbox Awareness

### Visible Sandbox State

Every terminal tab should show sandbox state.

Minimum indicators:

- filesystem mode
- network mode
- write permission
- Docker access
- approval state

Example:

```text
sandbox: workspace-write | network: disabled | docker: ask | approval: required
```

### Command Classification

Commands should be classified before execution.

Classes:

```text
ReadOnly
Test
Build
GitRead
GitWrite
FileWrite
DependencyInstall
Network
Docker
Destructive
SecretSensitive
Unknown
```

Examples:

| Command | Class | Default Decision |
| --- | --- | --- |
| `git status --short` | GitRead | Allow |
| `rg "Sandbox"` | ReadOnly | Allow |
| `python3 scripts/run_tests.py` | Test | AllowWithWarning |
| `git commit` | GitWrite | RequireApproval |
| `rm -rf audit` | Destructive | RequireApproval or Deny |
| `curl https://...` | Network | RequireApproval |
| `docker build .` | Docker | RequireApproval |
| `pip install ...` | DependencyInstall | RequireApproval |

### Policy Explanation

When blocked or gated, show the reason:

```text
Command requires approval.

Reason:
- writes to repository
- mutates git history

Command:
git commit -m "..."
```

When denied:

```text
Command denied by sandbox policy.

Reason:
- attempts unrestricted filesystem deletion
- target path is outside workspace
```

### Approval Flow

Approval prompt should appear in:

- terminal status line
- center conversation if command is task-critical
- right execution panel

Approval actions:

- approve once
- approve for task
- deny
- edit command
- explain risk

Never hide a waiting command in the terminal.

## Execution Logs

### Log Model

```text
ExecutionLogEntry
  id
  task_id
  session_id
  command
  argv
  cwd
  origin
  started_at
  ended_at
  duration_ms
  exit_code
  status
  sandbox_decision
  stdout_ref
  stderr_ref
  summary
  redactions
```

### Log Events

```text
command.queued
command.policy_evaluated
command.approval_requested
command.approval_granted
command.started
command.output
command.cancel_requested
command.completed
command.failed
command.timed_out
command.denied
```

### Log Retention

Recommended policy:

- keep full logs for active task
- keep summarized logs after task completion
- retain full logs for failed commands longer than successful commands
- redact secrets before persistence
- allow project setting for retention duration

Retention defaults:

```text
active task: full logs
completed task: summary + last 2,000 lines per command
failed command: summary + full redacted output
manual shell: command history only unless attached to task
```

### Redaction

Redact:

- environment variable values matching secret patterns
- tokens
- private keys
- passwords
- authorization headers
- `.env` values

Display:

```text
[REDACTED: token-like value]
```

Do not redact command structure unless necessary. Users need to understand what ran.

## Command History

### History Sources

Command history should include:

- manually typed shell commands
- ANUBIS task commands
- test reruns
- Git workflow commands
- Docker workflow commands

Each entry should record origin.

```text
HistoryEntry
  id
  command
  cwd
  origin
  task_id
  exit_code
  duration_ms
  last_run_at
  risk_class
```

### History UX

Features:

- arrow-key recall in Shell mode
- searchable history panel
- filter by task
- filter by success/failure
- filter by command class
- rerun with same cwd
- rerun after editing

Search examples:

```text
test
git
failed
docker build
task:unified-memory
```

### Sensitive Commands

Commands should not be persisted if they appear to include:

- inline passwords
- bearer tokens
- API keys
- private key material

Instead, store:

```text
[command hidden: secret-like inline value]
```

## Terminal and Conversation Integration

The terminal should feed structured evidence into the conversation.

Examples:

```text
Test command completed.
Result: failed
Duration: 4.2s
Failure: tests/test_memory.py::test_no_duplicate_indexing
```

Conversation blocks should link to terminal commands:

- Test Block -> terminal output
- Diff Block -> git diff command
- Review Block -> verification commands
- Error Block -> failed command output

The conversation should summarize. The terminal should preserve detail.

## Terminal and Execution Panel Integration

The right execution panel should show:

- active command
- phase
- sandbox decision
- elapsed time
- exit status
- recent errors

The terminal should show:

- raw stream
- command prompt
- command metadata

Do not duplicate full logs in the execution panel.

## Error Handling

### Command Fails

Show:

- exit code
- duration
- failing lines
- full output link
- suggested next action

Example:

```text
Command failed: exit 1
Duration: 1.8s

Likely failure:
ModuleNotFoundError: No module named 'pytest'

Actions:
Open output | Ask ANUBIS to investigate | Rerun
```

### Command Times Out

Show:

- timeout limit
- elapsed time
- last output
- whether process was killed
- rerun options

### Command Denied

Show:

- policy rule
- risk class
- command
- safer alternatives if known

### Stream Disconnects

If UI loses connection while command continues:

- keep process running if safe
- persist logs
- show reconnect state
- replay buffered output on reconnect

## Security Requirements

### Process Boundaries

Future real command execution should run through a dedicated runner boundary.

Recommended options:

1. Local restricted process runner
2. Containerized runner
3. Worktree-specific runner

The UI must not bypass the sandbox policy evaluator.

### Environment Handling

Rules:

- pass only approved environment variables
- redact environment output by default
- block secret display
- indicate when secrets are mounted or unavailable

### Working Directory Restrictions

Default:

```text
workspace root or approved worktree
```

Commands outside workspace should require approval or be denied, depending on policy.

### Network Awareness

Network commands should show:

- network allowed/disabled
- target host when detectable
- approval status

Network examples:

- package install
- curl/wget
- git push/fetch
- API calls

## Performance Targets

| Operation | Target |
| --- | ---: |
| Open terminal panel | `<100 ms` |
| Append visible output | `<50 ms` |
| Start read-only command | `<200 ms` plus process startup |
| Show first output chunk | `<100 ms` after process emits |
| Search current terminal buffer | `<150 ms` for recent output |
| Load command history | `<200 ms` |
| Restore active session | `<300 ms` |
| Stop command UI response | `<100 ms` |

Large logs must be virtualized.

## Accessibility

Requirements:

- selectable output text
- keyboard navigation
- visible focus states
- high-contrast status markers
- no color-only failure/success state
- screen-reader labels for command status
- reduced-motion mode for streaming indicators

## MVP Scope

Build first:

1. Bottom terminal panel with tabs.
2. Task Log mode.
3. Streaming stdout/stderr display.
4. Command metadata header.
5. Sandbox state indicator.
6. Execution log entries for ANUBIS commands.
7. Manual Shell mode with command history.
8. Stop/rerun/copy controls.
9. Redaction for obvious secret patterns.
10. Links from Test/Review blocks to terminal output.

Defer:

- full interactive PTY multiplexing
- remote terminal sessions
- multi-user terminal sharing
- containerized per-command runner
- advanced command classifier
- CI log streaming
- terminal replay export

## Acceptance Criteria

The integrated terminal is successful when:

- output streams live while commands run
- every command shows origin, cwd, sandbox state, and status
- blocked commands visibly wait for approval
- denied commands explain policy reasons
- completed commands are attached to execution logs
- command history is searchable and rerunnable
- test and Git evidence can be opened from conversation blocks
- secret-like values are redacted before persistence
- terminal output does not replace human-readable conversation summaries

## Final Architecture Contract

```text
Terminal UI
  displays live output and command controls

Terminal Session Manager
  owns tabs, shells, active commands, and history

Command Router
  classifies command origin and intent

Sandbox Policy Evaluator
  approves, denies, or gates execution

Execution Adapters
  run local, test, git, Docker, and diagnostic commands

Stream Multiplexer
  normalizes stdout, stderr, and structured events

Execution Log Store
  preserves redacted evidence for audit and review

Command History Store
  preserves safe rerunnable command history
```

This architecture gives ANUBIS a professional integrated terminal while preserving its central product posture: controlled local execution, explicit sandbox visibility, and auditable engineering evidence.
