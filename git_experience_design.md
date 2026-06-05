# ANUBIS Native Git Experience Design

Date: 2026-06-05

## Goal

Design a native Git experience for ANUBIS.

Required workflows:

- branch creation
- diff viewer
- commit workflow
- pull request workflow

Benchmark products:

- Claude Code
- Cursor

This is a product and architecture design, not an implementation plan that changes code.

## Product Intent

ANUBIS should make Git feel like a first-class part of the coding loop:

```text
understand -> plan -> edit -> test -> review diff -> commit -> open PR
```

The Git experience should be:

- explicit
- auditable
- reversible
- low-friction
- safe around user-authored changes
- optimized for human review before publication

ANUBIS should not behave like an invisible Git automation layer. It should never make destructive Git changes without a clear user decision.

## Benchmark Summary

### Claude Code

Observed benchmark behaviors from public Claude Code documentation:

- Desktop sessions can review changes through a file-by-file diff view before PR creation.
- Users can comment on diff lines and have Claude revise the changes.
- Claude can review its own current diff and leave comments in the diff view.
- PR status can be monitored after opening a pull request.
- Multiple Git sessions can be isolated using Git worktrees.
- Claude Code on the web can run tasks remotely, push changes to a new branch, and create a PR for review.

Design implications for ANUBIS:

- Diff review must be a core surface, not a terminal afterthought.
- Branch isolation should be available before work starts.
- PR creation should be tied to evidence: diff summary, tests, risks, and review notes.
- Review comments should become actionable feedback to the agent.
- CI status should appear in the workspace once a PR exists.

Sources:

- https://code.claude.com/docs/en/desktop
- https://support.claude.com/en/articles/12618689-claude-code-on-the-web

### Cursor

Observed benchmark behaviors from public Cursor documentation and product materials:

- Cursor has a Git sidebar experience.
- Cursor can generate commit messages from staged changes and repository history.
- Cursor can help resolve merge conflicts in chat.
- Cursor supports referencing Git context such as working state changes and branch differences.
- Cursor positions Git and checkpoints as part of the development lifecycle.
- Cursor advertises PR creation with summaries through agent/skill workflows.

Design implications for ANUBIS:

- Commit message generation should use staged changes plus commit history.
- Git context should be injectable into conversation and reviewer prompts.
- Merge conflicts should be surfaced as a guided repair workflow.
- Checkpoints should exist as ANUBIS task snapshots, but should not pollute repository history.
- PR summaries should be generated from actual diff, tests, and review evidence.

Sources:

- https://docs.cursor.com/en/more/ai-commit-message
- https://docs.cursor.com/en/context/%40-symbols/%40-git
- https://cursor.com/en-US/product

## Target Experience

Git should live in three places:

```text
Left rail:   status, branches, changed files
Center:      diff review, commit composer, PR composer
Right rail:  execution evidence, memory references, risk notes
Bottom:      raw git commands and logs when needed
```

The user should always know:

- current branch
- upstream branch
- dirty worktree state
- changed files
- staged files
- untracked files
- ANUBIS-authored changes
- user-authored changes
- test evidence attached to the change
- whether commit/PR actions are ready or blocked

## Core Principles

### 1. Git Is Review Infrastructure

Git is not merely a command runner. It is the review boundary for work produced by ANUBIS.

Every commit or PR should be backed by:

- task request
- plan
- changed files
- diff summary
- tests run
- reviewer decision
- risk assessment
- rollback path

### 2. Human Owns Publication

ANUBIS may propose, stage, commit, push, and open PRs only through explicit approval states.

Default policy:

```text
branch creation: allowed with confirmation
stage changes: allowed with confirmation
commit: requires confirmation
push: requires confirmation
open PR: requires confirmation
discard changes: requires strong confirmation
force push: disabled by default
merge PR: out of scope
```

### 3. Preserve User Work

ANUBIS must treat pre-existing local changes as protected.

Before a task starts, capture a baseline:

- HEAD commit
- branch name
- dirty file list
- file content hashes for dirty files
- staged state
- untracked file list

ANUBIS-authored changes should be distinguished from pre-existing changes whenever possible.

### 4. Prefer Small Reviewable Changes

The Git UX should encourage:

- one task per branch
- one logical change per commit
- focused PRs
- staged hunks when large diffs cross responsibilities
- generated commit messages that can be edited before use

### 5. Explain Before Action

Every Git action should state:

- what will happen
- which files are affected
- whether the action is reversible
- how to rollback

## Layout

### Left Git Panel

The left rail Git tab has five sections:

```text
Git
├── Status
├── Branches
├── Changes
├── Staged
└── Pull Request
```

#### Status Section

Fields:

- repository name
- current branch
- upstream branch
- ahead/behind count
- worktree cleanliness
- conflict state
- last fetched time
- active task branch marker

Example:

```text
main
origin/main
clean
last fetch: 4m ago
```

Dirty state example:

```text
feature/unified-memory
origin/feature/unified-memory
ahead 1, behind 0
8 changed, 3 staged, 2 untracked
```

#### Branches Section

Responsibilities:

- show current branch
- show recent local branches
- show remote tracking branch
- show ANUBIS task branches
- create branch
- checkout branch with safety checks
- delete local task branch after merge/close when safe

Branch display:

```text
* feature/unified-memory
  main
  audit/performance-baseline
  anubis/task/context-builder
```

Branch metadata:

- local or remote
- ahead/behind
- last commit time
- associated task
- PR status if known

#### Changes Section

Responsibilities:

- list modified, added, deleted, renamed, and untracked files
- filter by ANUBIS-authored vs pre-existing user changes
- show risk tags
- stage file
- stage hunk
- open diff
- discard ANUBIS change with confirmation

File row fields:

- status glyph
- path
- additions/deletions
- ownership marker
- risk marker

Ownership markers:

```text
User
ANUBIS
Mixed
Unknown
```

Risk markers:

```text
Config
Dependency
Runtime
Test
Generated
Secret-sensitive
```

#### Staged Section

Responsibilities:

- show staged files and staged hunks
- generate commit message from staged set
- warn if staged set mixes unrelated changes
- unstage file
- unstage hunk

The staged section is the commit boundary.

ANUBIS should not generate a final commit message from unstaged changes unless the user explicitly asks for a working-tree summary.

#### Pull Request Section

Responsibilities:

- show remote availability
- show PR readiness
- show target base branch
- show title and summary draft
- show CI status after PR exists
- expose open/create/update actions

Readiness states:

```text
Not ready: no commits
Ready: branch has commits and remote configured
Blocked: uncommitted changes
Blocked: tests failed
Blocked: no remote
Published: PR open
```

### Center Git Surfaces

Git should appear in the center panel when it is the active user task.

Center modes:

1. Diff viewer
2. Commit composer
3. PR composer
4. Conflict resolver
5. Branch creation dialog

## Branch Creation Workflow

### Entry Points

- Git panel `Create Branch`
- task start prompt
- command palette
- conversation command: `Create a branch for this task`

### Branch Dialog

Fields:

- branch name
- branch type
- base branch
- use worktree
- preserve current dirty changes
- associate with current task

Branch types:

```text
feature
fix
chore
audit
docs
experiment
```

Generated branch naming pattern:

```text
anubis/<type>/<slug>
```

Examples:

```text
anubis/feature/unified-memory-service
anubis/fix/rag-cache-duplication
anubis/audit/docker-optimization
```

### Branch Safety Rules

Before branch creation:

- read current branch
- read dirty state
- detect staged changes
- detect conflicts
- detect detached HEAD

If dirty work exists:

```text
Option A: create branch and keep current changes
Option B: create isolated worktree from clean base
Option C: cancel
```

If staged changes exist:

- preserve staging when staying in same worktree
- do not silently move staged changes to another branch
- explain what will carry over

If conflicts exist:

- block branch creation until conflicts are resolved or user explicitly creates an isolated clean worktree

### Worktree Support

Worktree mode should be available for parallel tasks.

Recommended path:

```text
.anubis/worktrees/<branch-slug>
```

Worktree metadata:

- task id
- branch
- base commit
- parent repository
- created time
- last active time

Benefits:

- isolates concurrent work
- avoids branch switching surprises
- protects active user changes
- enables side-by-side task sessions

Risks:

- more disk usage
- ignored files may be absent
- environment setup may need rerun

Mitigations:

- show worktree path clearly
- support `.anubis/worktreeinclude`
- detect missing env/config files without displaying secrets

## Diff Viewer

### Goals

The diff viewer should make review faster than reading raw `git diff`.

It should answer:

- what changed?
- why did it change?
- which files are risky?
- what tests validate it?
- what should I inspect first?

### Layout

```text
┌──────────────────────────────┬──────────────────────────────────────┐
│ Changed Files                │ Diff Detail                          │
│                              │                                      │
│ M core/memory.py       +42   │ @@ unified memory API                │
│ A tests/test_memory.py +88   │ - old line                           │
│ M README.md            +12   │ + new line                           │
│                              │                                      │
│ Filters                      │ Inline comments / agent notes        │
└──────────────────────────────┴──────────────────────────────────────┘
```

### File List

Each file row should show:

- path
- status
- additions/deletions
- staged/unstaged state
- ownership marker
- risk tag
- test coverage marker

Sort order:

1. high-risk files
2. runtime/config/dependency files
3. files with mixed ownership
4. source files
5. tests
6. docs
7. generated files

Filters:

- all
- staged
- unstaged
- ANUBIS-authored
- user-authored
- high-risk
- tests
- docs

### Diff Detail

Supported views:

- unified diff
- split diff
- semantic summary
- file-level summary
- hunk-level explanation

Default:

```text
split diff for code
unified diff for compact terminal mode
semantic summary collapsed above raw diff
```

### Inline Review

The user can:

- comment on a line
- ask ANUBIS to revise a hunk
- stage a hunk
- discard an ANUBIS-authored hunk
- copy diff context
- mark file reviewed

Inline comment states:

```text
Draft
Submitted to ANUBIS
Addressed
Unresolved
Dismissed
```

### Diff Summary

Every diff view should include a generated summary:

```text
Summary
- Adds UnifiedMemoryService facade.
- Routes repository/vault/conversation writes through one index path.
- Updates tests for duplicate indexing behavior.

Risk
- Qdrant collection naming changes may affect existing stored memories.

Evidence
- tests/test_memory.py passed
- No dependency changes
```

### Ownership Detection

ANUBIS should classify changes by comparing:

- baseline snapshot before task
- write operations performed by ANUBIS
- user edits during task
- file hash transitions

Classification:

```text
ANUBIS-authored: file changed only through ANUBIS write operations
User-authored: file was dirty before task and unchanged by ANUBIS
Mixed: pre-existing or concurrent user changes plus ANUBIS edits
Unknown: baseline unavailable
```

Mixed files require special review before commit.

## Commit Workflow

### Commit Readiness

Commit action is available only when:

- repository is not in conflict state
- staged changes exist
- user has reviewed or explicitly skipped review
- no protected user changes are staged accidentally

Recommended gates:

```text
Required: staged changes
Required: no merge conflicts
Required: explicit commit approval
Recommended: tests run after final staged set
Recommended: reviewer approval
Recommended: no mixed-ownership staged files
```

### Commit Composer

Fields:

- generated title
- generated body
- staged files
- test evidence
- risk notes
- commit style detection
- trailers

Composer layout:

```text
Commit

Title
[ fix(memory): prevent duplicate indexing              ]

Body
[ - route memory writes through UnifiedMemoryService    ]
[ - preserve existing collection names during migration ]
[ - add regression coverage for repeated indexing       ]

Staged files
3 files, +141 -32

Evidence
tests/test_memory.py passed

Actions
[Regenerate] [Edit] [Commit]
```

### Commit Message Generation

Inputs:

- staged diff
- recent commit history
- repository style
- task title
- reviewer summary
- test results

Style detection:

- Conventional Commits
- imperative short subject
- body/no-body preference
- ticket prefixes
- signoff or trailer style

Generation rules:

- describe only staged changes
- avoid invented intent
- mention tests only if actually run
- do not include hidden chain-of-thought
- include ANUBIS attribution only if configured

Example:

```text
fix(memory): avoid duplicate memory indexing

Route repository, vault, and conversation writes through a single
memory indexing path so repeated task context does not create duplicate
Qdrant records.

Tests:
- tests/test_memory.py
```

### Staging Model

Supported actions:

- stage all ANUBIS changes
- stage selected files
- stage selected hunks
- unstage selected files
- unstage selected hunks

Default recommendation:

```text
Stage ANUBIS changes only
```

If user-authored changes exist:

- show them separately
- do not stage by default
- require explicit selection

If mixed files exist:

- show hunk-level ownership when possible
- recommend hunk staging
- warn before staging whole file

### Commit Execution

Before committing, show final confirmation:

```text
Commit 3 staged files on branch anubis/fix/rag-cache?

Message:
fix(rag): cache embeddings by content hash

This will create one local commit.
It will not push to remote.
Rollback: git reset --soft HEAD~1
```

After commit:

- show commit hash
- show changed file count
- show remaining uncommitted changes
- offer PR creation
- offer copy hash

## Pull Request Workflow

### PR Readiness

PR action is available when:

- current branch is not the protected base branch
- branch has commits not on base
- remote is configured
- working tree is clean or user chooses to proceed with uncommitted changes excluded
- commit summary exists

Recommended gates:

```text
Required: non-base branch
Required: commits ahead of base
Required: remote configured
Required: explicit push/PR approval
Recommended: tests pass
Recommended: reviewer approval
Recommended: no secret-sensitive files changed
```

### PR Composer

Fields:

- title
- base branch
- compare branch
- summary
- implementation details
- test plan
- risk notes
- rollback
- linked issue
- labels
- draft toggle

Default PR mode:

```text
draft
```

The user may switch to ready-for-review.

### PR Summary Generation

Inputs:

- commits on branch
- full branch diff against base
- task plan
- final review
- test evidence
- risk assessment
- migration notes

Template:

```text
## Summary
- ...

## Tests
- ...

## Risks
- ...

## Rollback
- ...
```

Rules:

- summarize actual branch diff, not conversation hopes
- include failed tests if unresolved and user still creates draft PR
- avoid claiming migration completion unless code proves it
- distinguish implementation from design-only changes

### Push and PR Creation

Sequence:

1. fetch remote state
2. compare local branch with remote
3. detect force-push risk
4. push branch
5. create draft PR
6. attach generated summary
7. show PR URL
8. start CI monitoring if provider supports it

If remote branch exists:

- compare histories
- require confirmation before overwriting
- block force push by default

### PR Status

PR status panel shows:

- PR number
- URL
- draft/ready state
- base branch
- compare branch
- CI checks
- review comments
- mergeability
- last updated time

CI states:

```text
Pending
Passing
Failing
Cancelled
Unknown
```

When CI fails:

- show failing checks
- summarize logs if available
- offer `Investigate CI failure`
- preserve PR branch context

### PR Review Feedback Loop

ANUBIS should support:

- fetch PR comments
- map comments to files/hunks
- summarize requested changes
- plan fixes
- apply fixes with approval
- update branch
- regenerate PR summary if needed

Out of scope for initial native Git design:

- merge PR
- approve PR as a reviewer
- bypass branch protection
- manage repository permissions

## Merge Conflict Workflow

### Detection

Conflict state appears when:

- merge/rebase/cherry-pick conflict markers exist
- `git status` reports unmerged paths
- file parser detects unresolved conflict markers

### Conflict Resolver

Center panel mode:

```text
Conflict
├── file list
├── ours/theirs/base view
├── ANUBIS proposed resolution
├── test impact
└── accept/edit/retry controls
```

Actions:

- explain conflict
- propose resolution
- accept resolution for file
- edit manually
- mark resolved
- abort operation

Safety:

- never auto-accept conflict resolution without user approval
- always show original sides
- preserve base where available
- run focused tests after conflict resolution

## Git Context in Conversation

ANUBIS should make Git context addressable in prompts.

Suggested references:

```text
@git.status
@git.diff
@git.staged
@git.branch
@git.commits
@git.pr
```

Examples:

```text
Review @git.diff for bugs.
Generate a commit message for @git.staged.
Explain what changed on @git.branch compared with main.
Update the PR summary using @git.pr and latest test results.
```

Context Builder should treat Git references as structured context, not raw unlimited diff text.

Token budgeting:

- changed file summary first
- high-risk hunks second
- full hunks only when needed
- omit generated files by default
- compress unchanged context aggressively

## Data Model

### GitRepositoryState

```text
GitRepositoryState
  root_path
  current_branch
  head_sha
  upstream
  ahead_count
  behind_count
  is_dirty
  is_conflicted
  remotes
  last_fetch_at
```

### GitChangeSet

```text
GitChangeSet
  baseline_sha
  changed_files
  staged_files
  untracked_files
  ownership_map
  risk_tags
  generated_summary
```

### GitFileChange

```text
GitFileChange
  path
  status
  additions
  deletions
  staged
  ownership
  risk_tags
  hunks
```

### GitCommitDraft

```text
GitCommitDraft
  title
  body
  staged_files
  generated_from_sha
  tests
  risk_notes
  style
```

### PullRequestDraft

```text
PullRequestDraft
  title
  base_branch
  compare_branch
  body
  draft
  labels
  linked_issues
  tests
  risks
  rollback
```

### GitTaskBaseline

```text
GitTaskBaseline
  task_id
  branch
  head_sha
  dirty_files
  staged_files
  untracked_files
  file_hashes
  created_at
```

## Service Architecture

### Git Service

Responsibilities:

- read repository state
- compute status
- compute diffs
- create branches
- create worktrees
- stage/unstage changes
- create commits
- push branches
- create PRs through configured provider

### Diff Service

Responsibilities:

- parse diffs into file/hunk models
- compute semantic summaries
- detect generated files
- detect binary files
- map comments to hunks
- support side-by-side rendering data

### Ownership Service

Responsibilities:

- capture task baselines
- track ANUBIS writes
- classify file ownership
- detect mixed files
- warn before staging protected changes

### Commit Service

Responsibilities:

- inspect staged changes
- infer commit style
- generate commit draft
- validate commit readiness
- create commit after approval

### PR Service

Responsibilities:

- detect hosting provider
- generate PR draft
- push branch
- create PR
- poll PR/CI status
- fetch PR review comments

Supported providers for first version:

```text
GitHub via gh CLI or provider API
```

Future providers:

```text
GitLab
Bitbucket
Forgejo/Gitea
```

## Command Surface

### CLI Commands

Suggested commands:

```bash
anubis git status
anubis git branch create anubis/feature/context-builder
anubis git diff
anubis git diff --staged
anubis git stage --anubis
anubis git commit
anubis git pr
anubis git pr status
```

### Conversation Commands

Natural language examples:

```text
Create a branch for this task.
Show me the diff.
Review the staged changes.
Generate a commit message.
Commit the staged changes.
Open a draft PR.
Check PR status.
Investigate the failing PR check.
```

### Command Palette

Suggested commands:

```text
Git: Show Status
Git: Create Branch
Git: Show Diff
Git: Stage ANUBIS Changes
Git: Generate Commit Message
Git: Commit Staged Changes
Git: Create Draft PR
Git: Check PR Status
Git: Resolve Conflicts
```

## Safety and Policy

### Destructive Operations

Operations requiring strong confirmation:

- discard file changes
- discard hunk
- reset branch
- delete branch
- delete worktree
- abort merge/rebase
- force push

Strong confirmation should show:

- exact command
- affected files
- whether recovery is possible
- rollback instructions

### Blocked by Default

The following should be disabled unless explicitly configured:

- force push
- merge PR
- delete remote branch
- rewrite public branch history
- commit secret-looking files
- push with unresolved test failures in strict mode

### Secret Protection

Before staging, committing, or PR creation:

- scan changed files for secret-like patterns
- flag `.env`, key files, certificates, and token files
- never display secret values
- block commit in strict mode

### Dependency and Config Protection

Changes to these files should trigger elevated review:

- dependency manifests
- lockfiles
- Dockerfiles
- CI workflows
- deployment configs
- auth/security configs

## Rollback Strategy

### Local Commit Rollback

After commit:

```bash
git reset --soft HEAD~1
```

Use when:

- commit message is wrong
- staged set should be adjusted
- user wants to amend before push

### Local Branch Rollback

For ANUBIS task branches:

```bash
git switch main
git branch -D anubis/<type>/<slug>
```

Use only after confirming:

- branch is not needed
- commits are not unique or user accepts deletion
- no uncommitted work remains

### Worktree Rollback

For task worktrees:

```bash
git worktree remove .anubis/worktrees/<branch-slug>
```

Use only after:

- worktree is clean
- branch handling is decided

### PR Rollback

Options:

- close draft PR
- push corrective commit
- revert branch commit
- delete remote branch after PR closure

ANUBIS should recommend the least destructive option first.

## Performance Targets

| Operation | Target |
| --- | ---: |
| Read git status | `<150 ms` |
| Open changed file list | `<200 ms` |
| Open diff for small file | `<300 ms` |
| Open diff for large file | `<1 s` |
| Generate staged commit message | `<3 s` excluding model latency |
| Create local branch | `<300 ms` |
| Create worktree | `<2 s` excluding dependency setup |
| Create local commit | `<500 ms` |
| Push branch | network-bound |
| Create PR | network-bound |

Diff rendering should virtualize large files and large file lists.

## UX Details

### Empty States

Clean repository:

```text
No local changes.
Create a branch or start a task.
```

No staged changes:

```text
No staged changes.
Stage ANUBIS changes or select files manually.
```

No remote:

```text
No remote configured.
You can commit locally, but PR creation is unavailable.
```

### Warnings

Mixed ownership:

```text
This file contains both pre-existing user changes and ANUBIS changes.
Review hunks before staging.
```

Protected branch:

```text
You are on main.
Create a task branch before committing.
```

Failed tests:

```text
Tests failed after the current diff.
Create a draft PR only if this is intentional.
```

### Review Checklist

Before commit:

- changed files reviewed
- staged set is coherent
- generated files excluded unless intentional
- tests run or intentionally skipped
- secrets scan passed
- commit message edited or accepted

Before PR:

- branch pushed intentionally
- PR body reflects actual diff
- tests documented
- risks documented
- rollback documented
- draft/ready status chosen

## Competitive Positioning

### Compared With Claude Code

ANUBIS should match:

- file-by-file diff review
- inline feedback loop
- branch/PR creation
- CI status visibility
- isolated sessions through worktrees

ANUBIS should differentiate with:

- stricter local-first safety
- explicit ownership detection
- rollback shown before action
- memory references attached to Git review
- deterministic audit trail for every Git operation

### Compared With Cursor

ANUBIS should match:

- sidebar Git workflow
- AI commit message generation
- Git context references
- merge conflict assistance
- PR summary generation

ANUBIS should differentiate with:

- less editor-dependent workflow
- stronger task-level review evidence
- stricter staged-only commit generation
- explicit distinction between user and agent changes
- architecture-aware risk tagging

## MVP Scope

Build first:

1. Git status panel.
2. Branch creation with dirty-state checks.
3. Changed file list.
4. Diff viewer.
5. Stage/unstage files.
6. Commit message generation from staged changes.
7. Commit composer and local commit.
8. Draft PR composer for GitHub.
9. PR URL/status display.
10. Safety confirmations for destructive actions.

Defer:

- merge conflict resolution UI
- hunk-level ownership detection
- multi-provider PR support
- CI log summarization
- review comment ingestion
- automatic branch cleanup
- merge operations

## Acceptance Criteria

The native Git experience is successful when:

- a user can create a task branch without touching terminal Git commands
- a user can inspect all ANUBIS changes in a professional diff viewer
- a user can stage only ANUBIS-authored changes
- a user can generate and edit a commit message from staged changes
- ANUBIS refuses to commit accidental user changes by default
- a user can open a draft PR with summary, tests, risks, and rollback notes
- PR status is visible after publication
- destructive actions are reversible or clearly warned
- every Git action is recorded in the task audit trail

## Final Layout Contract

```text
Left Git Panel
  status, branches, changes, staged files, PR state

Center Git Surface
  diff viewer, commit composer, PR composer, conflict resolver

Bottom Terminal
  raw command output and manual fallback

Right Rail
  execution evidence, reviewer notes, memory references, risk tags
```

This design makes Git the delivery surface for ANUBIS work while preserving the product's core promise: local-first, auditable, human-controlled engineering automation.
