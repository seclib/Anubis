# User-First Redesign Proposal

This proposal refactors Anubis Desktop OS into a simple user-facing application while keeping the advanced architecture available in Developer Mode.

The main principle:

> Users should work with notes, documents, search, the assistant, extensions, and settings. They should not need to understand RAG, embeddings, vector databases, agent orchestration, Skill DNA, loop cognition, or internal runtime details.

## Product Shape

Anubis should feel like a personal knowledge workspace with an AI assistant.

The default app should answer these user questions:

- Where are my notes?
- Where are my documents?
- Can I search my knowledge?
- Can I ask the assistant?
- Can I add abilities?
- Can I change settings?

Advanced system state should still exist, but it should be hidden unless Developer Mode is enabled.

## Simplified Navigation

Default navigation should have six primary sections:

```text
Notes
Documents
Search
Assistant
Extensions
Settings
```

### Notes

Purpose: write and edit personal notes.

User-facing features:

- note list
- note editor
- create note
- rename note
- delete note
- save status
- recent notes
- folders or collections

Hidden technical behavior:

- notes are automatically indexed in the background
- note changes update memory automatically
- search data is refreshed without user action

### Documents

Purpose: collect files the user wants Anubis to remember.

User-facing features:

- import document
- view imported documents
- remove document
- document status: ready, processing, needs attention
- supported file hints

Hidden technical behavior:

- document chunking
- embedding creation
- vector database storage
- reindex queue

### Search

Purpose: search all notes and documents.

User-facing features:

- single search box
- results grouped by note or document
- result preview
- open result
- filter by notes, documents, or date

Hidden technical behavior:

- hybrid retrieval
- vector search
- keyword search
- ranking

### Assistant

Purpose: ask questions and get help.

User-facing features:

- chat input
- answer area
- source cards named "Used from your knowledge"
- action buttons: summarize, make checklist, rewrite, explain
- memory suggestion prompts

Hidden technical behavior:

- agent routing
- retrieval before answering
- tool execution
- multi-agent coordination

### Extensions

Purpose: manage extra abilities.

User-facing features:

- installed extensions
- enable or disable extension
- extension description
- extension health: ready, needs setup, disabled
- install from local folder
- update extension

Internal mapping:

- extensions are the user-facing name for skills and plugin-like abilities
- Skill DNA metadata remains internal
- skill graph remains available in Developer Mode

### Settings

Purpose: simple app preferences.

User-facing settings:

- vault location
- app theme
- start Anubis automatically
- background indexing on or off
- assistant model selection by friendly name
- backup location
- Developer Mode toggle

Advanced settings should be hidden unless Developer Mode is enabled.

## UI Redesign Proposal

### Default Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Anubis                         Search all knowledge...       │
├───────────────┬──────────────────────────────────────────────┤
│ Notes         │                                              │
│ Documents     │             Current Section                  │
│ Search        │                                              │
│ Assistant     │                                              │
│ Extensions    │                                              │
│ Settings      │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

### Navigation Rules

- The sidebar should use plain labels only.
- Technical labels should not appear in default navigation.
- System status should be compact and friendly.
- Errors should explain what the user can do next.
- Technical logs should be hidden unless Developer Mode is on.

### Status Language

Replace technical terms:

```text
RAG                  -> Knowledge search
Embeddings           -> Search helpers
Vector database      -> Knowledge index
Agent orchestration  -> Assistant workflow
Skill DNA            -> Extension details
Loop cognition       -> Assistant process
Qdrant               -> Search service
Chunks               -> Memory pieces
```

### Default Home Screen

The first screen should be useful immediately:

```text
Welcome back

[New note] [Import document] [Ask assistant]

Recent notes
Recent documents
Suggested actions
Knowledge status: Ready
```

The current Brain Dashboard should move behind Developer Mode.

## Beginner-Friendly Onboarding

On first launch, Anubis should show a short guided flow.

### Step 1: Welcome

Message:

```text
Welcome to Anubis.
Anubis helps you keep notes, search your knowledge, and ask an AI assistant for help.
```

Actions:

- Get started
- Skip setup

### Step 2: Choose Workspace

Message:

```text
Choose where Anubis should store your notes and memory.
```

Options:

- Use recommended location
- Choose another folder

### Step 3: Add First Knowledge

Message:

```text
Start by creating a note or importing a document.
```

Actions:

- Create first note
- Import document
- Do this later

### Step 4: Assistant Introduction

Message:

```text
Ask the assistant questions about your notes and documents.
```

Example prompts:

- Summarize my notes
- What should I work on next?
- Turn this into a checklist

### Step 5: Ready

Message:

```text
Anubis is ready.
Your knowledge will be prepared in the background.
```

Action:

- Open Anubis

## Automatic Background Indexing

Indexing should be automatic and quiet.

User-facing behavior:

- when a note is saved, Anubis prepares it for search
- when a document is imported, Anubis shows "Processing"
- when processing is finished, Anubis shows "Ready"
- if processing fails, Anubis shows "Needs attention"

Suggested visible states:

```text
Ready
Processing
Paused
Needs attention
```

Internal behavior:

- file watcher detects note changes
- indexing job queue receives changed paths
- changed notes/documents are chunked
- embeddings are regenerated
- Qdrant is updated
- UI receives progress updates

The user should never need to press "Reindex" in the default interface.

## Automatic RAG Management

RAG should be renamed and managed as "Knowledge Search."

Default behavior:

- Anubis starts the search service when needed
- Anubis checks if the knowledge index is healthy
- Anubis repairs or rebuilds the index automatically when safe
- Anubis explains problems in plain language

User-facing messages:

```text
Preparing your knowledge...
Your knowledge is ready.
Some documents need attention.
Search is paused because the local search service is not running.
```

Developer Mode can still show:

- Qdrant status
- collection name
- embedding count
- chunk count
- indexing logs

## Extension Manager For Skills

Skills should become "Extensions" in the default UI.

### Extension Card

Each extension should show:

```text
Name
Short description
Status
Enable/Disable toggle
Details button
```

Example:

```text
Writing Helper
Improves summaries, rewrites, and checklists.
Status: Ready
[Enabled]
```

### Extension Details

Default details:

- what it helps with
- when Anubis uses it
- whether it is enabled
- last updated

Developer details:

- skill id
- dependencies
- triggers
- mutation rules
- fitness values
- graph relationships
- source Markdown

## Developer Mode Design

Developer Mode should be a setting, not a default experience.

Location:

```text
Settings -> Advanced -> Developer Mode
```

When Developer Mode is enabled, show an additional sidebar item:

```text
Developer
```

### Developer Section

Developer section tabs:

```text
System Health
Knowledge Index
Agents
Skills
Cognitive Graph
Logs
Runtime
```

### System Health

Shows:

- backend status
- launcher status
- search service status
- desktop status
- process details

### Knowledge Index

Shows:

- Qdrant status
- collection name
- chunk count
- embedding count
- reindex controls
- indexing queue

### Agents

Shows:

- active agents
- current tasks
- last executions
- durations
- failures

### Skills

Shows:

- Skill DNA metadata
- dependencies
- triggers
- mutation rules
- fitness
- evolution history

### Cognitive Graph

Shows:

- Cytoscape graph
- skills
- agents
- memory clusters
- relationships
- evolution events
- filters
- node inspection

### Logs

Shows:

- launcher logs
- backend logs
- indexing logs
- assistant logs
- filters by component

### Runtime

Shows:

- loop cognition events
- tool calls
- self-modifying runtime status
- patch validation
- rollback history

## Folder Organization Proposal

The current code can evolve toward this organization.

```text
desktop/src/
  app/
    App.tsx
    routes.ts
    navigation.ts

  user/
    HomeView.tsx
    NotesView.tsx
    DocumentsView.tsx
    SearchView.tsx
    AssistantView.tsx
    ExtensionsView.tsx
    SettingsView.tsx
    OnboardingView.tsx

  developer/
    DeveloperView.tsx
    SystemHealthPanel.tsx
    KnowledgeIndexPanel.tsx
    AgentActivityPanel.tsx
    SkillSystemPanel.tsx
    CognitiveGraphView.tsx
    LogsPanel.tsx
    RuntimePanel.tsx

  shared/
    api.ts
    layout/
    components/
    hooks/
    styles/
```

Backend organization proposal:

```text
backend/
  api/routes/
    notes.py
    documents.py
    search.py
    assistant.py
    extensions.py
    settings.py
    developer.py

  services/
    indexing_service.py
    knowledge_service.py
    extension_service.py
    onboarding_service.py
    settings_service.py

  developer/
    brain_snapshot.py
    graph_snapshot.py
    runtime_snapshot.py
```

Naming rule:

- user-facing routes use simple product language
- developer routes expose technical details

Example:

```text
/search/query          user-facing search
/extensions            user-facing extension manager
/developer/brain       advanced system dashboard
/developer/graph       advanced graph diagnostics
```

## Migration Plan

### Phase 1: Navigation Shell

- Replace current top-heavy dashboard with sidebar navigation.
- Add Home, Notes, Documents, Search, Assistant, Extensions, Settings.
- Move Brain Dashboard and Cognitive Graph into Developer Mode.

### Phase 2: Onboarding

- Add first-launch state.
- Add onboarding screens.
- Create default welcome note.
- Show knowledge preparation status.

### Phase 3: Background Indexing

- Add indexing queue.
- Watch note/document changes.
- Run indexing automatically.
- Show plain status.

### Phase 4: Extension Manager

- Rename skills to extensions in the default UI.
- Add enable/disable state.
- Keep Skill DNA details in Developer Mode.

### Phase 5: Developer Mode

- Add Developer Mode setting.
- Move health, logs, graph, RAG internals, and runtime panels into Developer.
- Keep direct links for advanced users.

## Acceptance Criteria

The redesign is successful when:

- a new user can open Anubis and start writing without reading architecture docs
- the default UI does not mention RAG, embeddings, Qdrant, Skill DNA, or loop cognition
- search and assistant memory work automatically
- skills appear as extensions
- technical dashboards remain available in Developer Mode
- troubleshooting messages tell users what to do next
