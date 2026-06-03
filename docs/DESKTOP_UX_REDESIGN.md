# Anubis Desktop UX Redesign

Anubis Desktop should feel like a professional coding product: dense, fast, keyboard-driven, local-first, and explicit about what the autonomous system is doing.

Inspirations:

- Claude Code: calm conversation-first command flow
- Codex: task execution visibility and code-aware context
- Cursor: workspace, git, terminal, and assistant surfaces in one coding shell

## Product Principles

- The desktop app is an engineering cockpit, not a chatbot.
- Conversation is the command interface, not the whole product.
- Task execution, memory, terminal, git, and workspace state must remain visible while the user works.
- Every autonomous action needs traceability: plan, step, tool, result, review, memory reference.
- The UI should be quiet and information-dense, with restrained contrast and predictable panes.

## Main Layout

```text
+----------------------+-----------------------------------+--------------------------+
| Left Rail            | Center Conversation               | Right Inspector          |
|                      |                                   |                          |
| Workspace            | task thread                       | Task Execution           |
| Vault                | streamed response                 | active DAG               |
| Git                  | code/reference previews           | step status              |
|                      | prompt composer                   | reviewer result          |
|                      |                                   |                          |
+----------------------+-----------------------------------+--------------------------+
| Bottom Terminal                                                                     |
| sandbox shell, command output, test logs, execution logs                             |
+-------------------------------------------------------------------------------------+
```

### Left Pane

Purpose: repository and knowledge navigation.

Sections:

- Workspace
  - repo selector
  - file tree
  - open files
  - search results
- Vault
  - Obsidian/docs tree
  - memory notes
  - pinned references
- Git
  - branch
  - changed files
  - staged files
  - diff summary
  - PR status

Behavior:

- Sections are collapsible, but the pane remains persistent.
- File and memory items can be injected into the conversation as references.
- Git changes link to diff previews in the center or right inspector.

### Center Pane

Purpose: user intent, agent output, and code-aware conversation.

Content:

- Conversation thread
- Inline code snippets and referenced file cards
- Plan summaries
- Review summaries
- Prompt composer

Composer requirements:

- Supports file chips, memory chips, and selected task chips.
- `Enter` inserts newline; `Cmd/Ctrl+Enter` submits.
- Submit creates a task, not just a chat message.
- Shows active context budget and included references.

Conversation message types:

- user request
- planner plan
- executor progress summary
- reviewer verdict
- system event
- memory reference

### Bottom Terminal

Purpose: execution transparency without leaving the product.

Tabs:

- Terminal
- Test Output
- Tool Logs
- Sandbox Events

Behavior:

- Executor-owned commands stream here.
- User can inspect but not bypass the sandboxed execution path.
- Failed commands link to the relevant task step and reviewer issue.
- Output should be searchable and copyable.

### Right Pane

Purpose: task and memory inspection.

Sections:

- Task Execution
  - active task
  - DAG graph/list toggle
  - Planner, Executor, Reviewer stages
  - retries and failures
  - current sandbox
- Memory References
  - repo memory
  - docs/vault memory
  - conversation memory
  - relevance scores
  - source links

Behavior:

- Defaults to active task execution.
- Switches to memory reference details when a memory citation is selected.
- Reviewer verdicts remain sticky until superseded.

## Component Architecture

```text
DesktopShell
  AppFrame
    LeftActivityPane
      WorkspaceExplorer
      VaultExplorer
      GitPanel
    CenterConversationPane
      ConversationTimeline
      MessageRenderer
      ReferencePreview
      PromptComposer
    RightInspectorPane
      TaskExecutionPanel
      TaskGraphView
      StepTimeline
      ReviewerVerdictPanel
      MemoryReferencesPanel
    BottomTerminalPane
      TerminalTabs
      TerminalOutput
      TestOutput
      ToolLogStream
```

### Core Components

`DesktopShell`

- Owns pane layout, resizing, global keyboard shortcuts, and persistence of panel widths.
- Does not own business logic.

`LeftActivityPane`

- Owns workspace, vault, and git navigation.
- Emits selected references to shared state.

`CenterConversationPane`

- Owns the main task conversation.
- Renders messages from task events, not arbitrary chat-only state.

`PromptComposer`

- Builds task submission payload:
  - prompt
  - selected repo
  - selected files
  - selected memory references
  - execution mode

`RightInspectorPane`

- Owns the active task detail view.
- Displays DAG state, step execution, review verdicts, and memory references.

`BottomTerminalPane`

- Renders executor output streams.
- Groups output by task, step, and sandbox process.

## State Architecture

Split current chat-centric state into focused stores:

```text
workspaceStore
  repos
  activeRepo
  fileTree
  openFiles

conversationStore
  messages
  composer
  selectedReferences

taskStore
  activeTaskId
  tasks
  taskGraph
  stepStatuses
  reviewerVerdicts

terminalStore
  sessions
  activeTab
  outputByStep

memoryStore
  references
  selectedReference
  collections: repo | docs | conversations

gitStore
  branch
  changes
  staged
  prStatus
```

## Backend Contracts

Initial UI-facing APIs should align with the simplified Planner/Executor/Reviewer architecture:

- `GET /workspace/repos`
- `GET /workspace/{repo_id}/tree`
- `GET /git/{repo_id}/status`
- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/events`
- `GET /tasks/{task_id}/terminal`
- `GET /memory/search`
- `GET /memory/references/{task_id}`

Streaming channels:

- task events
- executor terminal output
- reviewer verdict updates
- memory reference updates

## Visual Direction

Style:

- professional dark UI
- compact pane headers
- small, readable type
- restrained borders
- no marketing hero treatment
- no oversized decorative cards

Recommended palette:

- background: near black neutral
- panels: layered charcoal
- borders: low-contrast zinc
- accents:
  - green for success
  - amber for warning/retry
  - red for failure/block
  - blue/cyan only for active selection and links

Density:

- Pane headers: 32-40px
- Toolbar buttons: icon-first with tooltips
- Task rows: 32-44px
- Terminal: monospace, compact line height

## Interaction Model

Primary flows:

1. User selects repo/files/memory in left pane.
2. User submits a task in center composer.
3. Planner plan appears in center and right task panel.
4. Executor output streams in bottom terminal.
5. Reviewer verdict appears in right panel and summarized in conversation.
6. Memory references stay visible and clickable.
7. Git panel shows resulting changes and PR readiness.

Keyboard:

- `Cmd/Ctrl+K`: command palette
- `Cmd/Ctrl+Enter`: submit task
- `Cmd/Ctrl+J`: toggle terminal
- `Cmd/Ctrl+B`: toggle left pane
- `Cmd/Ctrl+I`: toggle right inspector
- `Cmd/Ctrl+Shift+M`: focus memory references
- `Cmd/Ctrl+Shift+G`: focus git panel

## Migration Plan

1. Replace scaffold Tauri screen in `anubis/src/App.tsx` with `DesktopShell`.
2. Promote `src/app/layout/Layout.tsx` into a four-pane app frame.
3. Split `SystemStatusPanel` into `TaskExecutionPanel` and `MemoryReferencesPanel`.
4. Replace `AnubisView = chat | vault | tools | plugins | settings` with pane-local section state.
5. Introduce `taskStore`, `terminalStore`, `workspaceStore`, `gitStore`, and `memoryStore`.
6. Convert conversation messages to task-event-backed timeline items.
7. Add terminal stream view wired to executor events.
8. Add memory references view wired to `UnifiedMemoryService`.
9. Add git panel wired to git status and PR generation events.
10. Remove chat-only shell assumptions after task event streaming is stable.

## Non-Goals

- No landing page.
- No generic chatbot layout.
- No single-agent “thinking panel” as the main abstraction.
- No direct host terminal bypassing the executor sandbox.
- No memory agent UI; memory is a service-backed reference system.
