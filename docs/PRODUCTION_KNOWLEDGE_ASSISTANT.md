# Production Knowledge Assistant Refactor

## Goal

Refactor Anubis Desktop OS into a production-ready personal knowledge assistant.

The product should behave like a second brain:

- easy to open
- easy to understand
- reliable by default
- helpful without setup anxiety
- powerful without exposing internal machinery

Priority:

> User experience over system complexity.

## Product Promise

Anubis helps users collect, write, search, and ask questions about their personal knowledge.

The default experience should feel like:

```text
My library
My notes
My search
My assistant
My settings
```

It should not feel like:

```text
RAG system
Agent framework
Vector database console
Skill runtime
Graph laboratory
```

## User View

The production app has five primary sections:

```text
Library
Notes
Search
Assistant
Settings
```

Everything else is hidden behind internal services or Developer Mode.

## Hidden System View

These systems remain available internally:

```text
RAG system
Agent orchestration
Memory system
Skill system
Graph engine
```

They should not be visible in the default UI.

Developer Mode can expose them for debugging, testing, and advanced inspection.

## Simplified Architecture

### Product-Level Architecture

```text
Desktop App
  -> Knowledge API
  -> Background Worker
  -> Assistant API
  -> Settings API
```

The user-facing app should talk to a small set of stable product interfaces.

### Internal Architecture

```text
Knowledge API
  -> notes service
  -> document service
  -> search service
  -> indexing service
  -> memory service

Assistant API
  -> assistant service
  -> retrieval service
  -> agent runtime
  -> tool runtime

Extensions API
  -> skill service
  -> plugin service
  -> graph service

Developer API
  -> system health
  -> logs
  -> RAG diagnostics
  -> agent diagnostics
  -> graph diagnostics
```

### Rule

The frontend should not know whether knowledge comes from Markdown, Qdrant, embeddings, chunks, agents, or tools.

The frontend should ask product questions:

```text
list my notes
import this document
search my knowledge
ask the assistant
show processing status
save settings
```

The backend decides how to fulfill them.

## Single Backend Interfaces

Create stable user-facing interfaces:

```text
/library
/notes
/documents
/search
/assistant
/settings
```

Advanced interfaces move behind:

```text
/developer
```

### Library Interface

Purpose:

Unified view of saved knowledge.

Responsibilities:

- list recent notes
- list recent documents
- show import status
- show knowledge readiness
- provide quick actions

Example product response:

```json
{
  "status": "ready",
  "recent_items": [],
  "processing": [],
  "needs_attention": []
}
```

### Notes Interface

Purpose:

Read and write notes.

Responsibilities:

- create note
- read note
- update note
- rename note
- delete note
- list notes

Hidden behavior:

- enqueue indexing after save
- update search metadata
- refresh memory in the background

### Documents Interface

Purpose:

Import and manage documents.

Responsibilities:

- drag and drop import
- list documents
- show processing state
- remove document
- retry failed processing

Hidden behavior:

- extract text
- split into searchable pieces
- create search data
- store document metadata

### Search Interface

Purpose:

Instant search across everything.

Responsibilities:

- search notes
- search documents
- return previews
- return filters
- open result target

Hidden behavior:

- keyword search
- semantic search
- ranking
- source normalization

### Assistant Interface

Purpose:

Chat with Anubis.

Responsibilities:

- send message
- stream answer
- show sources
- suggest next actions
- save useful answer as note

Hidden behavior:

- retrieve relevant knowledge
- choose tools
- route agent steps
- preserve memory

### Settings Interface

Purpose:

Control user preferences.

Responsibilities:

- workspace location
- theme
- startup behavior
- background processing
- backup location
- Developer Mode toggle

## UI Redesign

### App Shell

```text
┌──────────────────────────────────────────────────────────────┐
│ Anubis                                      Search...        │
├───────────────┬──────────────────────────────────────────────┤
│ Library       │                                              │
│ Notes         │                                              │
│ Search        │                Active screen                 │
│ Assistant     │                                              │
│ Settings      │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

Design priorities:

- calm layout
- obvious actions
- no technical labels
- persistent global search
- clear processing status
- fewer panels on screen at once

### Library Screen

Purpose:

The home screen for the user's knowledge.

```text
Library

[Import Documents] [Create Note] [Ask Assistant]

Knowledge Status
Ready

Recent
- Meeting Notes
- Research Summary
- Project Brief.pdf

Processing
- annual-report.pdf    Preparing...
```

What to remove from default Library:

- backend status
- Qdrant status
- agent status
- launcher internals
- raw logs
- chunk counts
- embedding counts

### Notes Screen

Purpose:

Focused writing.

```text
Notes

┌───────────────┬─────────────────────────────────────────────┐
│ Search notes  │ Note title                                  │
│               │                                             │
│ All notes     │ Write here...                               │
│ Favorites     │                                             │
│ Recent        │                                             │
│               │ Saved                                       │
└───────────────┴─────────────────────────────────────────────┘
```

Required actions:

- new note
- save
- rename
- delete
- ask about this note

### Search Screen

Purpose:

Instant search across notes and documents.

```text
Search

Search all knowledge...

Filters: All | Notes | Documents | Recent

Results
- Meeting Notes
  "The launch plan needs..."
- Project Brief.pdf
  "Primary audience..."
```

Search should feel immediate:

- update while typing
- show loading only when necessary
- keep previous results visible while updating

### Assistant Screen

Purpose:

Chat-based knowledge assistant.

```text
Assistant

Suggested:
[Summarize my notes] [Find action items] [Explain this document]

You: What should I focus on next?

Anubis: Based on your notes...

Used from your knowledge:
[Meeting Notes] [Project Brief]

Ask Anubis...
```

Assistant rules:

- show sources in friendly language
- allow saving answer as note
- allow follow-up questions
- never show agent routing or tool internals by default

### Settings Screen

Purpose:

Simple preferences.

```text
Settings

Workspace
Location: Anubis folder        [Change]

Appearance
Theme: System                  [Change]

Knowledge
Prepare knowledge automatically [On]

Backup
Backup location: Not set       [Choose]

Advanced
Developer Mode                 [Off]
```

## New App Flow

### First Launch

```text
Open Anubis
  -> Welcome
  -> Choose workspace
  -> Create note or import document
  -> Library
```

### Daily Use

```text
Open Anubis
  -> Library
  -> Review recent knowledge
  -> Search or ask Assistant
  -> Create or update notes
```

### Document Ingestion

```text
Drag document into Library
  -> Document appears as Processing
  -> Background worker extracts text
  -> Search index updates
  -> Status changes to Ready
  -> Document appears in Search and Assistant sources
```

### Note Update

```text
Edit note
  -> Save
  -> Status: Saved
  -> Background indexing starts
  -> Knowledge status updates quietly
  -> Search and Assistant use latest content
```

### Search Flow

```text
Type in global search
  -> Instant local results
  -> Better ranked results arrive
  -> Open result or ask Assistant about results
```

### Assistant Flow

```text
Ask question
  -> Anubis searches knowledge automatically
  -> Assistant answers
  -> Friendly source cards appear
  -> User saves answer or asks follow-up
```

## Background Processing

Background processing should be automatic and reliable.

### Processing Queue

Use one queue for:

- note indexing
- document text extraction
- document indexing
- search metadata refresh
- memory refresh

User-facing states:

```text
Ready
Preparing
Paused
Needs attention
```

Internal states:

```text
queued
extracting
chunking
embedding
indexing
complete
failed
```

Only user-facing states appear in the default UI.

### Stability Rules

- saving notes must never wait on indexing
- failed indexing must not block note editing
- assistant should still answer when search is degraded
- document processing failures should be retryable
- app startup should not require every internal service to be ready

## Drag And Drop Document Ingestion

Default behavior:

1. User drops files into Library.
2. App shows accepted files.
3. App shows "Preparing."
4. App processes files in background.
5. Files become searchable.

Supported initial states:

```text
Ready
Preparing
Unsupported file
Needs attention
```

Drop zone copy:

```text
Drop documents here

Anubis will prepare them so you can search and ask questions.
```

## Developer Mode

Developer Mode is hidden by default.

Enable from:

```text
Settings -> Advanced -> Developer Mode
```

Developer Mode contains:

```text
Agent Dashboard
RAG Monitor
Qdrant Tools
Skill Manager
Runtime Inspector
System Logs
```

### Agent Dashboard

Shows:

- active agents
- current tasks
- execution durations
- failures

### RAG Monitor

Shows:

- indexing pipeline
- chunk count
- embedding count
- retrieval diagnostics

### Qdrant Tools

Shows:

- service status
- collection status
- point count
- rebuild controls

### Skill Manager

Shows:

- installed skills
- dependencies
- Skill DNA
- evolution tracking
- graph relationships

### Runtime Inspector

Shows:

- loop events
- tool calls
- runtime patches
- rollback state

### System Logs

Shows:

- launcher logs
- backend logs
- indexing logs
- assistant logs
- filters by component

## Recommended Folder Organization

Frontend:

```text
desktop/src/
  app/
    App.tsx
    navigation.ts
    routes.ts

  screens/
    LibraryScreen.tsx
    NotesScreen.tsx
    SearchScreen.tsx
    AssistantScreen.tsx
    SettingsScreen.tsx
    OnboardingScreen.tsx

  developer/
    DeveloperMode.tsx
    AgentDashboard.tsx
    RagMonitor.tsx
    QdrantTools.tsx
    SkillManager.tsx
    RuntimeInspector.tsx
    SystemLogs.tsx

  shared/
    api/
    components/
    hooks/
    layout/
    styles/
```

Backend:

```text
backend/
  api/routes/
    library.py
    notes.py
    documents.py
    search.py
    assistant.py
    settings.py
    developer.py

  services/
    library_service.py
    document_service.py
    indexing_service.py
    search_service.py
    assistant_service.py
    settings_service.py

  internal/
    rag/
    agents/
    memory/
    skills/
    graph/
```

Principle:

> User-facing routes use product language. Internal modules can keep technical names.

## Implementation Phases

### Phase 1: Product Shell

- Add sidebar navigation.
- Add Library, Notes, Search, Assistant, Settings.
- Move current Brain Dashboard into Developer Mode.
- Remove technical terms from default UI.

### Phase 2: Unified Interfaces

- Add `/library`.
- Add `/documents`.
- Add `/search`.
- Add `/assistant`.
- Keep advanced routes under `/developer`.

### Phase 3: Background Processing

- Add processing queue.
- Add automatic note indexing.
- Add drag and drop document ingestion.
- Add processing status.

### Phase 4: Assistant Simplification

- Rename source display to "Used from your knowledge."
- Hide tool and agent details.
- Add suggested prompts.
- Add save-answer-as-note.

### Phase 5: Developer Mode

- Add Developer Mode toggle.
- Move RAG, Qdrant, agents, skills, graph, runtime, and logs into Developer Mode.
- Keep diagnostics available without polluting the default app.

## Acceptance Criteria

The refactor is successful when:

- a new user can import a document without knowing what indexing is
- a new user can search immediately after adding knowledge
- a new user can ask the assistant without understanding RAG
- the default UI does not expose RAG, Qdrant, embeddings, agent orchestration, Skill DNA, loop cognition, or graph internals
- advanced systems remain available in Developer Mode
- note editing stays fast even while background work is running
- failures are shown as helpful user actions, not technical errors

## Final Product Positioning

Anubis should be described as:

```text
A private knowledge assistant for notes, documents, search, and AI help.
```

Not:

```text
A local autonomous multi-agent RAG framework.
```
