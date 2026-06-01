import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ChatMessage, loadNotes, saveNote, searchWorkspace, sendChat, SearchResult, WorkspaceNote } from "./api";
import "./styles.css";

type View = "Library" | "Notes" | "Search" | "Assistant" | "Settings";

const storageKey = "anubis.desktop.notes";

const starterNotes: WorkspaceNote[] = [
  {
    id: "welcome",
    title: "Welcome",
    path: "Notes/Welcome.md",
    updatedAt: new Date().toISOString(),
    content:
      "# Welcome to Anubis\n\nAnubis is your local workspace for notes, documents, search, and conversation.\n\n- Write in Markdown\n- Drop files into the Library\n- Ask the assistant about what you are working on\n"
  },
  {
    id: "daily",
    title: "Daily Notes",
    path: "Notes/Daily Notes.md",
    updatedAt: new Date().toISOString(),
    content: "# Daily Notes\n\n## Today\n\n- Review project direction\n- Capture ideas as they appear\n- Ask for help when a thread gets fuzzy\n"
  }
];

const navigation: Array<{ view: View; label: string }> = [
  { view: "Library", label: "📁 Library" },
  { view: "Notes", label: "📝 Notes" },
  { view: "Search", label: "🔍 Search" },
  { view: "Assistant", label: "🤖 Assistant" }
];

function readLocalNotes(): WorkspaceNote[] {
  const saved = window.localStorage.getItem(storageKey);
  if (!saved) return starterNotes;
  try {
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : starterNotes;
  } catch {
    return starterNotes;
  }
}

function persistLocalNotes(notes: WorkspaceNote[]) {
  window.localStorage.setItem(storageKey, JSON.stringify(notes));
}

function makeId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function titleFromContent(content: string) {
  const heading = content
    .split("\n")
    .find((line) => line.trim().startsWith("#"))
    ?.replace(/^#+\s*/, "")
    .trim();
  return heading || "Untitled";
}

function mockAssistantReply(message: string, note: WorkspaceNote | null) {
  const scope = note ? `I looked at "${note.title}" while thinking about this.` : "I looked across your open workspace.";
  if (message.trim().endsWith("?")) {
    return `${scope}\n\nA useful next step is to turn the question into a short note, then add two or three concrete examples underneath it.`;
  }
  return `${scope}\n\nI can help refine this into a clearer note, outline, or action list.`;
}

function localSearch(notes: WorkspaceNote[], query: string): SearchResult[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  return notes
    .map((note) => {
      const index = note.content.toLowerCase().indexOf(normalized);
      const excerpt =
        index >= 0
          ? note.content.slice(Math.max(0, index - 72), Math.min(note.content.length, index + 180)).trim()
          : note.content.slice(0, 180).trim();
      const score = `${note.title} ${note.path} ${note.content}`.toLowerCase().includes(normalized) ? 1 : 0;
      return { id: note.id, title: note.title, path: note.path, excerpt, score };
    })
    .filter((result) => result.score > 0)
    .map(({ score: _score, ...result }) => result);
}

function Sidebar({
  view,
  status,
  onNavigate
}: {
  view: View;
  status: string;
  onNavigate: (view: View) => void;
}) {
  return (
    <aside className="sidebar">
      <button className="brand-button" onClick={() => onNavigate("Notes")}>
        <strong>🧠 Anubis</strong>
        <span>Desktop OS</span>
      </button>
      <nav aria-label="Workspace">
        {navigation.map((item) => (
          <button className={view === item.view ? "active" : ""} key={item.view} onClick={() => onNavigate(item.view)}>
            {item.label}
          </button>
        ))}
      </nav>
      <button className={view === "Settings" ? "settings active" : "settings"} onClick={() => onNavigate("Settings")}>
        ⚙️ Settings
      </button>
      <span className="save-state">{status}</span>
    </aside>
  );
}

function Editor({
  view,
  notes,
  activeNote,
  searchQuery,
  searchResults,
  onCreateNote,
  onOpenNote,
  onImportFiles,
  onUpdateNote,
  onSearch
}: {
  view: View;
  notes: WorkspaceNote[];
  activeNote: WorkspaceNote | null;
  searchQuery: string;
  searchResults: SearchResult[];
  onCreateNote: () => void;
  onOpenNote: (id: string) => void;
  onImportFiles: (files: FileList | null) => void;
  onUpdateNote: (content: string) => void;
  onSearch: (query: string) => void;
}) {
  if (view === "Library") {
    return (
      <section className="center-panel">
        <header className="titlebar">
          <div>
            <h1>Library</h1>
            <p>{notes.length} documents in your workspace</p>
          </div>
          <label className="primary-action">
            Import
            <input multiple type="file" onChange={(event) => onImportFiles(event.currentTarget.files)} />
          </label>
        </header>
        <div className="drop-card">
          <strong>Drop documents here</strong>
          <span>Plain text and Markdown files become part of your workspace.</span>
        </div>
        <div className="document-grid">
          {notes.map((note) => (
            <button className="document-card" key={note.id} onClick={() => onOpenNote(note.id)}>
              <strong>{note.title}</strong>
              <span>{note.path}</span>
              <p>{note.content.replace(/[#*_`>-]/g, "").slice(0, 140)}</p>
            </button>
          ))}
        </div>
      </section>
    );
  }

  if (view === "Search") {
    return (
      <section className="center-panel">
        <header className="titlebar">
          <div>
            <h1>Search</h1>
            <p>Find notes and documents instantly.</p>
          </div>
        </header>
        <input
          autoFocus
          className="search-field"
          placeholder="Search your workspace"
          value={searchQuery}
          onChange={(event) => onSearch(event.target.value)}
        />
        <div className="result-list">
          {searchResults.map((result) => (
            <button key={result.id} onClick={() => onOpenNote(result.id)}>
              <strong>{result.title}</strong>
              <span>{result.path}</span>
              <p>{result.excerpt}</p>
            </button>
          ))}
          {searchQuery && searchResults.length === 0 ? <p className="empty-state">No matches yet.</p> : null}
        </div>
      </section>
    );
  }

  if (view === "Assistant") {
    return (
      <section className="center-panel quiet-panel">
        <h1>Assistant</h1>
        <p>Use the panel on the right to ask questions, shape notes, and work through ideas.</p>
      </section>
    );
  }

  if (view === "Settings") {
    return (
      <section className="center-panel">
        <header className="titlebar">
          <div>
            <h1>Settings</h1>
            <p>Local workspace preferences</p>
          </div>
        </header>
        <div className="settings-grid">
          <section>
            <strong>Autosave</strong>
            <span>Enabled</span>
          </section>
          <section>
            <strong>Storage</strong>
            <span>Local desktop workspace</span>
          </section>
          <section>
            <strong>Assistant</strong>
            <span>Powered by your knowledge base</span>
          </section>
        </div>
      </section>
    );
  }

  return (
    <section className="center-panel editor-panel">
      <header className="titlebar">
        <div>
          <h1>{activeNote?.title || "Untitled"}</h1>
          <p>{activeNote?.path || "Notes/Untitled.md"}</p>
        </div>
        <button className="primary-action" onClick={onCreateNote}>
          New note
        </button>
      </header>
      <textarea
        className="markdown-editor"
        placeholder="Write in Markdown..."
        spellCheck
        value={activeNote?.content || ""}
        onChange={(event) => onUpdateNote(event.target.value)}
      />
    </section>
  );
}

function ChatPanel({
  messages,
  input,
  onInput,
  onSend
}: {
  messages: ChatMessage[];
  input: string;
  onInput: (value: string) => void;
  onSend: () => void;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  return (
    <aside className="chat-panel">
      <header>
        <div>
          <h2>Assistant</h2>
          <p>Powered by your knowledge base</p>
        </div>
      </header>
      <div className="messages">
        {messages.map((message) => (
          <article className={message.role} key={message.id}>
            <p>{message.content}</p>
          </article>
        ))}
        <div ref={endRef} />
      </div>
      <div className="chat-input">
        <textarea
          placeholder="Ask Anubis..."
          value={input}
          onChange={(event) => onInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) onSend();
          }}
        />
        <button onClick={onSend}>Send</button>
      </div>
    </aside>
  );
}

function App() {
  const [view, setView] = useState<View>("Notes");
  const [notes, setNotes] = useState<WorkspaceNote[]>(() => readLocalNotes());
  const [activeId, setActiveId] = useState(() => readLocalNotes()[0]?.id || "");
  const [status, setStatus] = useState("Saved");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "hello",
      role: "assistant",
      content: "Hi. I can help summarize notes, find connections, and turn rough ideas into something clearer."
    }
  ]);
  const autosaveRef = useRef<number | null>(null);

  const activeNote = useMemo(() => notes.find((note) => note.id === activeId) || notes[0] || null, [activeId, notes]);

  useEffect(() => {
    loadNotes().then((remoteNotes) => {
      if (!remoteNotes || remoteNotes.length === 0) return;
      setNotes(remoteNotes);
      setActiveId(remoteNotes[0].id);
      persistLocalNotes(remoteNotes);
    });
  }, []);

  useEffect(() => {
    persistLocalNotes(notes);
  }, [notes]);

  async function handleSearch(query: string) {
    setSearchQuery(query);
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    const remoteResults = await searchWorkspace(query);
    setSearchResults(remoteResults ?? localSearch(notes, query));
  }

  function handleCreateNote() {
    const note: WorkspaceNote = {
      id: makeId(),
      title: "Untitled",
      path: "Notes/Untitled.md",
      updatedAt: new Date().toISOString(),
      content: "# Untitled\n\n"
    };
    setNotes((current) => [note, ...current]);
    setActiveId(note.id);
    setView("Notes");
    setStatus("Saved");
  }

  function handleOpenNote(id: string) {
    setActiveId(id);
    setView("Notes");
  }

  function handleUpdateNote(content: string) {
    setStatus("Saving...");
    const updatedAt = new Date().toISOString();
    setNotes((current) =>
      current.map((note) =>
        note.id === activeNote?.id
          ? {
              ...note,
              title: titleFromContent(content),
              path: `Notes/${titleFromContent(content)}.md`,
              updatedAt,
              content
            }
          : note
      )
    );
    if (autosaveRef.current) window.clearTimeout(autosaveRef.current);
    autosaveRef.current = window.setTimeout(async () => {
      const nextNote = notes.find((note) => note.id === activeNote?.id);
      if (nextNote) await saveNote({ ...nextNote, content, title: titleFromContent(content), updatedAt });
      setStatus("Saved");
    }, 650);
  }

  async function handleImportFiles(files: FileList | null) {
    if (!files?.length) return;
    const imported = await Promise.all(
      Array.from(files).map(async (file) => {
        const content = await file.text();
        const title = titleFromContent(content) || file.name.replace(/\.[^.]+$/, "");
        return {
          id: makeId(),
          title,
          path: `Library/${file.name}`,
          content: content.startsWith("#") ? content : `# ${title}\n\n${content}`,
          updatedAt: new Date().toISOString()
        };
      })
    );
    setNotes((current) => [...imported, ...current]);
    setActiveId(imported[0].id);
    setView("Library");
    setStatus("Imported");
  }

  async function handleSendMessage() {
    const text = chatInput.trim();
    if (!text) return;
    const userMessage: ChatMessage = { id: makeId(), role: "user", content: text };
    setMessages((current) => [...current, userMessage]);
    setChatInput("");
    const answer = (await sendChat(text, activeNote)) ?? mockAssistantReply(text, activeNote);
    setMessages((current) => [...current, { id: makeId(), role: "assistant", content: answer }]);
  }

  return (
    <main
      className="app-shell"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        handleImportFiles(event.dataTransfer.files);
      }}
    >
      <Sidebar status={status} view={view} onNavigate={setView} />
      <Editor
        activeNote={activeNote}
        notes={notes}
        searchQuery={searchQuery}
        searchResults={searchResults}
        view={view}
        onCreateNote={handleCreateNote}
        onImportFiles={handleImportFiles}
        onOpenNote={handleOpenNote}
        onSearch={handleSearch}
        onUpdateNote={handleUpdateNote}
      />
      <ChatPanel input={chatInput} messages={messages} onInput={setChatInput} onSend={handleSendMessage} />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
