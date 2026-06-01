# Anubis UX Architecture

## Product Direction

Anubis Desktop OS should become a user-first knowledge assistant.

The user should experience Anubis as:

> A private workspace for saving knowledge, writing notes, finding information, and asking an AI assistant for help.

The user should not experience Anubis as:

> An AI framework, agent runtime, vector database interface, RAG dashboard, or developer tool.

Advanced systems remain available, but only inside **Developer Mode**.

## Target User

Primary user:

- non-technical
- wants help organizing information
- wants to write notes and import documents
- wants to ask questions about their own knowledge
- does not want to manage services, indexes, agents, databases, or logs

Design principle:

> Every default screen should answer a normal user question, not expose an internal system.

## 1. New Navigation Structure

Default navigation:

```text
Library
Notes
AI Assistant
Search
Settings
```

Developer Mode navigation appears only when enabled:

```text
Developer Mode
  Agent Dashboard
  RAG Monitor
  Qdrant Tools
  Skill Manager
  Runtime Inspector
  System Logs
```

### Navigation Model

```text
Anubis
├── Library
├── Notes
├── AI Assistant
├── Search
├── Settings
└── Developer Mode
    ├── Agent Dashboard
    ├── RAG Monitor
    ├── Qdrant Tools
    ├── Skill Manager
    ├── Runtime Inspector
    └── System Logs
```

### Default Sidebar

```text
┌──────────────────┐
│ Anubis           │
├──────────────────┤
│ Library          │
│ Notes            │
│ AI Assistant     │
│ Search           │
│ Settings         │
└──────────────────┘
```

### Developer Sidebar

When Developer Mode is enabled:

```text
┌──────────────────┐
│ Anubis           │
├──────────────────┤
│ Library          │
│ Notes            │
│ AI Assistant     │
│ Search           │
│ Settings         │
├──────────────────┤
│ Developer Mode   │
│ Agent Dashboard  │
│ RAG Monitor      │
│ Qdrant Tools     │
│ Skill Manager    │
│ Runtime Inspector│
│ System Logs      │
└──────────────────┘
```

## Section Definitions

### Library

Purpose:

The home for all saved knowledge.

Includes:

- imported documents
- note collections
- recently used items
- knowledge preparation status
- quick actions

Primary actions:

- import document
- create note
- ask about this library
- open recent item

User language:

- "Preparing your knowledge"
- "Ready to search"
- "Some files need attention"

Avoid:

- RAG
- embeddings
- vector database
- chunks
- Qdrant

### Notes

Purpose:

Focused writing and editing.

Includes:

- note list
- folders or collections
- editor
- save status
- note actions

Primary actions:

- new note
- edit note
- rename note
- delete note
- ask assistant about note

### AI Assistant

Purpose:

Conversation with Anubis.

Includes:

- chat
- suggested prompts
- source cards
- recent conversations
- assistant actions

Primary actions:

- ask question
- summarize selected knowledge
- create checklist
- explain document
- rewrite note

Source cards should say:

```text
Used from your knowledge
```

Not:

```text
Retrieved chunks
RAG sources
Vector matches
```

### Search

Purpose:

Find anything saved in Anubis.

Includes:

- global search bar
- filters
- result previews
- open in context
- ask assistant about results

Filters:

- all
- notes
- documents
- recent
- favorites

### Settings

Purpose:

Simple control over user preferences.

Includes:

- workspace location
- theme
- startup behavior
- backup location
- AI assistant preference
- background knowledge preparation
- Developer Mode toggle

Advanced settings are hidden unless Developer Mode is enabled.

## 2. Onboarding Flow

Onboarding should be short and confidence-building.

### Onboarding Map

```text
Welcome
  -> Choose Workspace
  -> Add First Knowledge
  -> Meet The Assistant
  -> Ready
```

### Step 1: Welcome

Goal:

Explain Anubis in one sentence.

Screen copy:

```text
Welcome to Anubis

Anubis helps you save knowledge, write notes, search everything, and ask an AI assistant for help.

[Get Started]
```

### Step 2: Choose Workspace

Goal:

Let the user know where their information will live.

Screen copy:

```text
Choose where Anubis should keep your knowledge.

Recommended: use the Anubis workspace folder.

[Use Recommended Folder] [Choose Another Folder]
```

### Step 3: Add First Knowledge

Goal:

Get the user to create or import something.

Screen copy:

```text
Add your first knowledge.

You can create a note now or import a document.

[Create Note] [Import Document] [Do This Later]
```

### Step 4: Meet The Assistant

Goal:

Teach the core loop: save knowledge, ask questions.

Screen copy:

```text
Ask Anubis about your knowledge.

Try:
- Summarize my notes
- What should I focus on next?
- Turn this into a checklist

[Continue]
```

### Step 5: Ready

Goal:

Confirm the app is ready and reduce anxiety about background work.

Screen copy:

```text
You're ready.

Anubis will prepare your knowledge in the background so it can be searched and used by the assistant.

[Open Anubis]
```

## 3. First-Run Experience

After onboarding, the user lands on **Library**.

### Empty Library State

```text
┌────────────────────────────────────────────────────────────┐
│ Library                                                    │
├────────────────────────────────────────────────────────────┤
│ Start building your knowledge                              │
│                                                            │
│ Add notes or documents so Anubis can help you search,      │
│ summarize, and answer questions.                           │
│                                                            │
│ [Create Note] [Import Document] [Ask Assistant]            │
└────────────────────────────────────────────────────────────┘
```

### First Note Created

```text
┌────────────────────────────────────────────────────────────┐
│ Library                                                    │
├────────────────────────────────────────────────────────────┤
│ Knowledge status: Preparing                                │
│                                                            │
│ Recent                                                     │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Welcome Note                                         │   │
│ │ Updated just now                                     │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                            │
│ Suggested next step: Ask Anubis to summarize this note     │
└────────────────────────────────────────────────────────────┘
```

### Ready State

```text
┌────────────────────────────────────────────────────────────┐
│ Library                                                    │
├────────────────────────────────────────────────────────────┤
│ Knowledge status: Ready                                   │
│                                                            │
│ [Import Document] [Create Note] [Ask About Library]        │
│                                                            │
│ Recent Notes                  Recent Documents             │
│ - Welcome Note                - Project Brief.pdf          │
│ - Meeting Ideas               - Research Notes.md          │
└────────────────────────────────────────────────────────────┘
```

## 4. User Workflow Diagrams

### Workflow: Create A Note And Ask About It

```text
Open Anubis
  -> Notes
  -> New Note
  -> Write content
  -> Save
  -> Anubis prepares knowledge in background
  -> AI Assistant
  -> Ask: "Summarize my note"
  -> Assistant answers with source card
```

### Workflow: Import A Document And Search It

```text
Open Anubis
  -> Library
  -> Import Document
  -> Select file
  -> Status: Processing
  -> Status: Ready
  -> Search
  -> Type query
  -> Open result
```

### Workflow: Ask The Assistant Across All Knowledge

```text
Open Anubis
  -> AI Assistant
  -> Ask a question
  -> Anubis searches saved knowledge automatically
  -> Assistant answers
  -> User opens source cards if needed
```

### Workflow: Enable Developer Mode

```text
Open Anubis
  -> Settings
  -> Advanced
  -> Enable Developer Mode
  -> Developer Mode appears in sidebar
  -> Open advanced tools
```

### Workflow: Manage Extensions

Default user flow:

```text
Open Anubis
  -> Settings
  -> Extensions
  -> Enable or disable extension
  -> Return to Assistant
```

Developer flow:

```text
Open Anubis
  -> Developer Mode
  -> Skill Manager
  -> Inspect skill details
  -> Review dependencies and evolution
```

## 5. Screen Mockups

### Main App Shell

```text
┌───────────────────────────────────────────────────────────────┐
│ Anubis                                      Search knowledge   │
├──────────────┬────────────────────────────────────────────────┤
│ Library      │                                                │
│ Notes        │                                                │
│ AI Assistant │                 Current screen                 │
│ Search       │                                                │
│ Settings     │                                                │
└──────────────┴────────────────────────────────────────────────┘
```

### Library Screen

```text
┌───────────────────────────────────────────────────────────────┐
│ Library                                                       │
│ Your saved knowledge, notes, and documents                    │
├───────────────────────────────────────────────────────────────┤
│ [Create Note] [Import Document] [Ask About Library]           │
│                                                               │
│ Knowledge Status                                              │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ Ready                                                     │ │
│ │ 24 notes · 8 documents                                   │ │
│ └───────────────────────────────────────────────────────────┘ │
│                                                               │
│ Recent                                                        │
│ ┌──────────────────────┐ ┌──────────────────────┐            │
│ │ Meeting Notes        │ │ Product Ideas        │            │
│ │ Updated today        │ │ Updated yesterday    │            │
│ └──────────────────────┘ └──────────────────────┘            │
└───────────────────────────────────────────────────────────────┘
```

### Notes Screen

```text
┌───────────────────────────────────────────────────────────────┐
│ Notes                                           [New Note]     │
├──────────────────┬────────────────────────────────────────────┤
│ Search notes     │ Title                                      │
│                  │                                            │
│ Welcome Note     │ Write your note here...                    │
│ Meeting Notes    │                                            │
│ Product Ideas    │                                            │
│                  │                                            │
│                  │ Saved                                      │
└──────────────────┴────────────────────────────────────────────┘
```

### AI Assistant Screen

```text
┌───────────────────────────────────────────────────────────────┐
│ AI Assistant                                                  │
│ Ask questions about your notes and documents                  │
├───────────────────────────────────────────────────────────────┤
│ Suggested                                                     │
│ [Summarize my notes] [Make a checklist] [Find open questions] │
│                                                               │
│ You: What should I focus on next?                             │
│                                                               │
│ Anubis: Based on your recent notes, the next useful step is... │
│                                                               │
│ Used from your knowledge                                      │
│ ┌──────────────────────┐ ┌──────────────────────┐            │
│ │ Meeting Notes        │ │ Product Ideas        │            │
│ └──────────────────────┘ └──────────────────────┘            │
│                                                               │
│ Ask Anubis...                                      [Send]     │
└───────────────────────────────────────────────────────────────┘
```

### Search Screen

```text
┌───────────────────────────────────────────────────────────────┐
│ Search                                                        │
├───────────────────────────────────────────────────────────────┤
│ Search all knowledge...                                       │
│                                                               │
│ Filters: [All] [Notes] [Documents] [Recent] [Favorites]       │
│                                                               │
│ Results                                                       │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ Meeting Notes                                             │ │
│ │ "...decision about the launch plan..."                    │ │
│ └───────────────────────────────────────────────────────────┘ │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ Project Brief.pdf                                         │ │
│ │ "...main audience is non-technical users..."              │ │
│ └───────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### Settings Screen

```text
┌───────────────────────────────────────────────────────────────┐
│ Settings                                                      │
├───────────────────────────────────────────────────────────────┤
│ Workspace                                                     │
│ Location: Anubis folder                         [Change]      │
│                                                               │
│ Appearance                                                    │
│ Theme: System                                  [Change]       │
│                                                               │
│ Knowledge                                                     │
│ Prepare knowledge in background                [On]           │
│                                                               │
│ Backup                                                        │
│ Backup location: Not set                       [Choose]       │
│                                                               │
│ Advanced                                                      │
│ Developer Mode                                 [Off]          │
└───────────────────────────────────────────────────────────────┘
```

### Developer Mode Screen

```text
┌───────────────────────────────────────────────────────────────┐
│ Developer Mode                                                │
├──────────────────┬────────────────────────────────────────────┤
│ Agent Dashboard  │ Advanced system tools                      │
│ RAG Monitor      │                                            │
│ Qdrant Tools     │ These screens show internal system details │
│ Skill Manager    │ for debugging, development, and inspection.│
│ Runtime Inspector│                                            │
│ System Logs      │                                            │
└──────────────────┴────────────────────────────────────────────┘
```

## 6. Recommended Information Architecture

### User-Facing IA

```text
Anubis
├── Library
│   ├── Recent
│   ├── Documents
│   ├── Collections
│   └── Knowledge Status
├── Notes
│   ├── All Notes
│   ├── Folders
│   ├── Editor
│   └── Note Actions
├── AI Assistant
│   ├── Chat
│   ├── Suggested Prompts
│   ├── Used From Your Knowledge
│   └── Conversation History
├── Search
│   ├── Global Search
│   ├── Filters
│   ├── Results
│   └── Result Preview
└── Settings
    ├── Workspace
    ├── Appearance
    ├── Knowledge Preparation
    ├── Backup
    ├── Extensions
    └── Advanced
```

### Developer Mode IA

```text
Developer Mode
├── Agent Dashboard
│   ├── Active Agents
│   ├── Current Tasks
│   ├── Last Executions
│   └── Durations
├── RAG Monitor
│   ├── Index Status
│   ├── Chunk Count
│   ├── Embedding Count
│   └── Rebuild Controls
├── Qdrant Tools
│   ├── Service Status
│   ├── Collection Info
│   ├── Point Counts
│   └── Diagnostics
├── Skill Manager
│   ├── Skills
│   ├── Dependencies
│   ├── Skill DNA
│   ├── Evolution Tracking
│   └── Cognitive Graph
├── Runtime Inspector
│   ├── Loop Events
│   ├── Tool Calls
│   ├── Runtime Patches
│   └── Rollback History
└── System Logs
    ├── Launcher Logs
    ├── Backend Logs
    ├── Indexing Logs
    └── Assistant Logs
```

## Language Strategy

Default UI terms:

```text
Knowledge
Library
Notes
Documents
Assistant
Search
Extensions
Preparing
Ready
Needs attention
```

Developer-only terms:

```text
RAG
Qdrant
embeddings
chunks
agent orchestration
Skill DNA
loop cognition
self-modifying runtime
vector database
```

## Transformation Summary

Before:

```text
AI framework with visible internals
```

After:

```text
Knowledge management application powered by AI
```

The technology remains powerful, but the default product experience becomes calm, understandable, and task-focused.
