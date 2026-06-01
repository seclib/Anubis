# Anubis Desktop OS UI

## Layout

```text
+----------------------+------------------------------+--------------------------+
| Vault Markdown       | Markdown Editor              | Agent + RAG Insights     |
|                      |                              |                          |
| note tree            | active file path             | chat input               |
| refresh              | save                         | answer                   |
| drag note path       | inject selection             | sources used             |
| open note            | raw Markdown editing         | chunk previews           |
+----------------------+------------------------------+--------------------------+
```

## Components

- `VaultPane`: lists Markdown notes from `GET /notes`, opens notes and supports drag start with the note path.
- `EditorPane`: raw Markdown textarea, save action, selection tracking and selection injection.
- `AgentPane`: chat input, answer view and RAG source cards.
- `RagSourceCard`: shows source path, heading, score, line range and text preview.

## Interactions

- Click note: load content with `GET /notes/{path}`.
- Edit Markdown: update local editor state immediately.
- Save: persist with `PUT /notes`.
- Select text then inject: sends `remember: selected text` to `POST /agent/chat`.
- Drag note path: drag a file from the vault list into the editor to open it.
- Chat: sends message to `POST /agent/chat`, then displays answer and chunks used.
- Keyboard: `Ctrl+Enter` or `Cmd+Enter` sends chat.

## UI To Backend Flow

```text
open note
  UI -> GET /notes/{path}
  backend -> vault read
  UI <- Markdown content

save note
  UI -> PUT /notes
  backend -> vault write
  watcher -> chunk -> embed -> Qdrant

chat
  UI -> POST /agent/chat
  backend -> rag_query -> chunks -> answer
  UI <- answer + chunks_used

inject selection
  UI -> POST /agent/chat remember:...
  backend -> write Markdown memory
  watcher/indexer -> Qdrant
```

## UX Principles

- Three persistent columns, no modal-heavy workflow.
- Raw Markdown first, preview later if needed.
- RAG sources stay visible next to the answer.
- Save and inject are one-click actions.
- Qdrant is invisible to the user except through source cards.
