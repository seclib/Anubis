import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import "./ui/styles.css";

type View = "library" | "notes" | "search" | "assistant" | "settings";
type Role = "user" | "assistant";

type Note = {
  id: string;
  title: string;
  body: string;
  updatedAt: string;
};

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
};

const starterNotes: Note[] = [
  {
    id: "home",
    title: "Home",
    updatedAt: "Just now",
    body:
      "# Home\n\nWelcome to Anubis.\n\nUse this space for notes, drafts, research, and decisions. The assistant can help with whatever you are writing.",
  },
  {
    id: "ideas",
    title: "Ideas",
    updatedAt: "Today",
    body: "# Ideas\n\n- Capture useful thoughts\n- Turn notes into plans\n- Keep the writing simple",
  },
  {
    id: "draft",
    title: "Project Draft",
    updatedAt: "Yesterday",
    body: "# Project Draft\n\nWrite freely here. Autosave keeps your current note ready while you work.",
  },
];

const initialConversation: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content: "I can help summarize notes, draft ideas, and search across your workspace.",
  },
];

export default function App() {
  const [activeView, setActiveView] = useState<View>("notes");
  const [notes, setNotes] = useState<Note[]>(starterNotes);
  const [activeNoteId, setActiveNoteId] = useState(starterNotes[0].id);
  const [saveState, setSaveState] = useState<"Saved" | "Saving...">("Saved");
  const [searchQuery, setSearchQuery] = useState("");

  const activeNote = notes.find((note) => note.id === activeNoteId) ?? notes[0];

  useEffect(() => {
    loadNotes().then((loadedNotes) => {
      if (loadedNotes.length > 0) {
        setNotes(loadedNotes);
        setActiveNoteId(loadedNotes[0].id);
      }
    });
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setSaveState("Saving...");
      await saveNote(activeNote);
      setSaveState("Saved");
    }, 650);

    return () => window.clearTimeout(timer);
  }, [activeNote]);

  function updateActiveNote(body: string) {
    setNotes((currentNotes) =>
      currentNotes.map((note) =>
        note.id === activeNoteId
          ? {
              ...note,
              body,
              title: titleFromMarkdown(body) || note.title,
              updatedAt: "Just now",
            }
          : note,
      ),
    );
  }

  function createNote() {
    const nextNote: Note = {
      id: crypto.randomUUID(),
      title: "Untitled",
      body: "# Untitled\n\n",
      updatedAt: "Just now",
    };
    setNotes((currentNotes) => [nextNote, ...currentNotes]);
    setActiveNoteId(nextNote.id);
    setActiveView("notes");
  }

  return (
    <main className="h-screen overflow-hidden bg-neutral-950 text-neutral-100">
      <div className="grid h-full grid-cols-[236px_minmax(420px,1fr)_390px]">
        <Sidebar activeView={activeView} onChangeView={setActiveView} onCreateNote={createNote} />
        <EditorPanel
          activeView={activeView}
          note={activeNote}
          notes={notes}
          saveState={saveState}
          searchQuery={searchQuery}
          onChangeNote={updateActiveNote}
          onChangeSearch={setSearchQuery}
          onSelectNote={(noteId) => {
            setActiveNoteId(noteId);
            setActiveView("notes");
          }}
          onCreateNote={createNote}
        />
        <ChatPanel note={activeNote} />
      </div>
    </main>
  );
}

function Sidebar({
  activeView,
  onChangeView,
  onCreateNote,
}: {
  activeView: View;
  onChangeView: (view: View) => void;
  onCreateNote: () => void;
}) {
  const items: Array<{ id: View; label: string }> = [
    { id: "library", label: "📁 Library" },
    { id: "notes", label: "📝 Notes" },
    { id: "search", label: "🔍 Search" },
    { id: "assistant", label: "🤖 Assistant" },
    { id: "settings", label: "Settings" },
  ];

  return (
    <aside className="flex min-h-0 flex-col border-r border-neutral-800 bg-neutral-950/95 px-3 py-4">
      <div className="mb-5 flex items-center justify-between px-2">
        <h1 className="text-base font-semibold tracking-tight text-neutral-50">🧠 Anubis</h1>
        <span className="rounded-full bg-emerald-400/10 px-2 py-1 text-[11px] font-medium text-emerald-300">
          Saved
        </span>
      </div>

      <button
        type="button"
        onClick={onCreateNote}
        className="mb-4 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-left text-sm text-neutral-100 transition hover:border-neutral-700 hover:bg-[#181818]"
      >
        New note
      </button>

      <nav className="space-y-1">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onChangeView(item.id)}
            className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
              activeView === item.id
                ? "bg-neutral-800 text-neutral-50"
                : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-100"
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="mt-auto rounded-lg border border-neutral-800 bg-neutral-900/50 p-3">
        <p className="text-xs leading-5 text-neutral-400">A quiet place to write, organize, and ask for help.</p>
      </div>
    </aside>
  );
}

function EditorPanel({
  activeView,
  note,
  notes,
  saveState,
  searchQuery,
  onChangeNote,
  onChangeSearch,
  onSelectNote,
  onCreateNote,
}: {
  activeView: View;
  note: Note;
  notes: Note[];
  saveState: "Saved" | "Saving...";
  searchQuery: string;
  onChangeNote: (body: string) => void;
  onChangeSearch: (query: string) => void;
  onSelectNote: (noteId: string) => void;
  onCreateNote: () => void;
}) {
  if (activeView === "library") {
    return <LibraryView notes={notes} onSelectNote={onSelectNote} onCreateNote={onCreateNote} />;
  }

  if (activeView === "search") {
    return (
      <SearchView
        notes={notes}
        query={searchQuery}
        onChangeQuery={onChangeSearch}
        onSelectNote={onSelectNote}
      />
    );
  }

  if (activeView === "settings") {
    return <SettingsView />;
  }

  if (activeView === "assistant") {
    return <AssistantView note={note} />;
  }

  return <NotesView note={note} saveState={saveState} onChangeNote={onChangeNote} />;
}

function NotesView({
  note,
  saveState,
  onChangeNote,
}: {
  note: Note;
  saveState: "Saved" | "Saving...";
  onChangeNote: (body: string) => void;
}) {
  return (
    <section className="flex min-h-0 flex-col bg-neutral-950">
      <header className="flex h-14 items-center justify-between border-b border-neutral-800 px-8">
        <div>
          <h2 className="text-sm font-medium text-neutral-100">{note.title}</h2>
          <p className="text-xs text-neutral-500">Updated {note.updatedAt}</p>
        </div>
        <span className="text-xs text-neutral-500">{saveState}</span>
      </header>

      <textarea
        value={note.body}
        onChange={(event) => onChangeNote(event.target.value)}
        spellCheck="true"
        className="h-full flex-1 resize-none bg-neutral-950 px-12 py-10 font-serif text-[17px] leading-8 text-neutral-200 outline-none placeholder:text-neutral-600"
        placeholder="Start writing..."
      />
    </section>
  );
}

function LibraryView({
  notes,
  onSelectNote,
  onCreateNote,
}: {
  notes: Note[];
  onSelectNote: (noteId: string) => void;
  onCreateNote: () => void;
}) {
  return (
    <section className="min-h-0 overflow-auto bg-neutral-950 px-8 py-7">
      <div className="mb-7 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-neutral-50">Library</h2>
          <p className="mt-1 text-sm text-neutral-500">{notes.length} documents</p>
        </div>
        <button
          type="button"
          onClick={onCreateNote}
          className="rounded-lg bg-neutral-100 px-3 py-2 text-sm font-medium text-neutral-950 transition hover:bg-white"
        >
          New note
        </button>
      </div>

      <div className="space-y-2">
        {notes.map((note) => (
          <button
            type="button"
            key={note.id}
            onClick={() => onSelectNote(note.id)}
            className="w-full rounded-lg border border-[#242424] bg-neutral-900/40 p-4 text-left transition hover:border-neutral-700 hover:bg-neutral-900"
          >
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-medium text-neutral-100">{note.title}</h3>
              <span className="text-xs text-neutral-500">{note.updatedAt}</span>
            </div>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-neutral-400">{plainPreview(note.body)}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

function SearchView({
  notes,
  query,
  onChangeQuery,
  onSelectNote,
}: {
  notes: Note[];
  query: string;
  onChangeQuery: (query: string) => void;
  onSelectNote: (noteId: string) => void;
}) {
  const [results, setResults] = useState<Note[]>([]);

  useEffect(() => {
    let cancelled = false;

    searchNotes(query, notes).then((nextResults) => {
      if (!cancelled) {
        setResults(nextResults);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [notes, query]);

  return (
    <section className="min-h-0 overflow-auto bg-neutral-950 px-8 py-7">
      <h2 className="text-xl font-semibold text-neutral-50">Search</h2>
      <input
        value={query}
        onChange={(event) => onChangeQuery(event.target.value)}
        className="mt-5 w-full rounded-xl border border-neutral-800 bg-neutral-900 px-4 py-3 text-sm text-neutral-100 outline-none transition placeholder:text-neutral-600 focus:border-neutral-600"
        placeholder="Search your notes..."
      />

      <div className="mt-6 space-y-2">
        {(query ? results : notes).map((note) => (
          <button
            type="button"
            key={note.id}
            onClick={() => onSelectNote(note.id)}
            className="w-full rounded-lg p-3 text-left transition hover:bg-neutral-900"
          >
            <h3 className="text-sm font-medium text-neutral-100">{note.title}</h3>
            <p className="mt-1 line-clamp-2 text-sm leading-6 text-neutral-500">{plainPreview(note.body)}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

function SettingsView() {
  return (
    <section className="min-h-0 overflow-auto bg-neutral-950 px-8 py-7">
      <h2 className="text-xl font-semibold text-neutral-50">Settings</h2>
      <div className="mt-6 max-w-xl space-y-3">
        <SettingRow title="Theme" value="Dark" />
        <SettingRow title="Autosave" value="On" />
        <SettingRow title="Assistant" value="Ready" />
      </div>
    </section>
  );
}

function AssistantView({ note }: { note: Note }) {
  return (
    <section className="flex min-h-0 flex-col bg-neutral-950 px-8 py-7">
      <h2 className="text-xl font-semibold text-neutral-50">Assistant</h2>
      <p className="mt-2 max-w-xl text-sm leading-6 text-neutral-500">
        Ask questions in the panel on the right. It can help with the current note, rewrite passages, or turn rough ideas into a clear draft.
      </p>

      <div className="mt-8 max-w-2xl rounded-xl border border-neutral-800 bg-neutral-900/40 p-5">
        <p className="text-xs uppercase tracking-wide text-neutral-500">Current note</p>
        <h3 className="mt-2 text-lg font-medium text-neutral-100">{note.title}</h3>
        <p className="mt-3 line-clamp-5 text-sm leading-6 text-neutral-400">{plainPreview(note.body)}</p>
      </div>
    </section>
  );
}

function SettingRow({ title, value }: { title: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-[#242424] bg-neutral-900/40 px-4 py-3">
      <span className="text-sm text-neutral-300">{title}</span>
      <span className="text-sm text-neutral-500">{value}</span>
    </div>
  );
}

function ChatPanel({ note }: { note: Note }) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialConversation);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [messages, loading]);

  async function submitMessage(event?: FormEvent) {
    event?.preventDefault();
    const prompt = input.trim();
    if (!prompt || loading) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: prompt,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setLoading(true);

    const answer = await askAssistant(prompt, note);
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: answer,
      },
    ]);
    setLoading(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitMessage();
    }
  }

  return (
    <aside className="flex min-h-0 flex-col border-l border-neutral-800 bg-[#0f0f0f]">
      <header className="border-b border-neutral-800 px-5 py-4">
        <h2 className="text-sm font-semibold text-neutral-50">Assistant</h2>
        <p className="mt-1 text-xs text-neutral-500">Powered by your knowledge base</p>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-5">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${
              message.role === "user"
                ? "ml-auto bg-neutral-100 text-neutral-950"
                : "mr-auto border border-neutral-800 bg-neutral-900 text-neutral-200"
            }`}
          >
            {message.content}
          </div>
        ))}
        {loading && (
          <div className="mr-auto flex max-w-[88%] items-center gap-2 rounded-2xl border border-neutral-800 bg-neutral-900 px-4 py-3">
            <span className="h-2 w-2 animate-pulse rounded-full bg-neutral-400" />
            <span className="h-2 w-2 animate-pulse rounded-full bg-neutral-500 [animation-delay:140ms]" />
            <span className="h-2 w-2 animate-pulse rounded-full bg-neutral-600 [animation-delay:280ms]" />
          </div>
        )}
      </div>

      <form onSubmit={submitMessage} className="border-t border-neutral-800 p-4">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          className="min-h-[92px] w-full resize-none rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-3 text-sm leading-6 text-neutral-100 outline-none transition placeholder:text-neutral-600 focus:border-neutral-600"
          placeholder="Ask about this note..."
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="mt-3 w-full rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </aside>
  );
}

async function askAssistant(prompt: string, note: Note): Promise<string> {
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: prompt,
        note: {
          title: note.title,
          body: note.body,
        },
      }),
    });

    if (response.ok) {
      const data = (await response.json()) as { answer?: string; message?: string };
      return data.answer ?? data.message ?? mockAnswer(prompt, note);
    }
  } catch {
    return mockAnswer(prompt, note);
  }

  return mockAnswer(prompt, note);
}

async function saveNote(note: Note): Promise<void> {
  try {
    await fetch("/api/save-note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(note),
    });
  } catch {
    const stored = window.localStorage.getItem("anubis-notes");
    const currentNotes = stored ? safeParseNotes(stored) : [];
    const exists = currentNotes.some((currentNote) => currentNote.id === note.id);
    const nextNotes = exists
      ? currentNotes.map((currentNote) => (currentNote.id === note.id ? note : currentNote))
      : [note, ...currentNotes];
    window.localStorage.setItem("anubis-notes", JSON.stringify(nextNotes));
  }
}

async function loadNotes(): Promise<Note[]> {
  try {
    const response = await fetch("/api/load-notes", { method: "POST" });
    if (response.ok) {
      const data = (await response.json()) as { notes?: Note[] };
      return Array.isArray(data.notes) ? data.notes : [];
    }
  } catch {
    const stored = window.localStorage.getItem("anubis-notes");
    if (!stored) {
      return [];
    }

    return safeParseNotes(stored);
  }

  return [];
}

function safeParseNotes(value: string): Note[] {
  try {
    const parsed = JSON.parse(value) as Note[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function searchNotes(query: string, notes: Note[]): Promise<Note[]> {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return [];
  }

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (response.ok) {
      const data = (await response.json()) as { notes?: Note[] };
      if (Array.isArray(data.notes)) {
        return data.notes;
      }
    }
  } catch {
    return notes.filter((note) => `${note.title} ${note.body}`.toLowerCase().includes(normalizedQuery));
  }

  return notes.filter((note) => `${note.title} ${note.body}`.toLowerCase().includes(normalizedQuery));
}

function mockAnswer(prompt: string, note: Note): string {
  const lowerPrompt = prompt.toLowerCase();

  if (lowerPrompt.includes("summar")) {
    return `Summary of "${note.title}": ${plainPreview(note.body).slice(0, 180)}.`;
  }

  if (lowerPrompt.includes("title")) {
    return `A clearer title could be "${titleFromMarkdown(note.body) || note.title}".`;
  }

  return `I read "${note.title}". A useful next step is to clarify the main point, add any missing details, and turn the strongest ideas into short action items.`;
}

function titleFromMarkdown(markdown: string): string {
  const firstHeading = markdown
    .split("\n")
    .find((line) => line.trim().startsWith("#"))
    ?.replace(/^#+\s*/, "")
    .trim();

  return firstHeading ?? "";
}

function plainPreview(markdown: string): string {
  return markdown
    .replace(/^#+\s*/gm, "")
    .split("*")
    .join("")
    .split("_")
    .join("")
    .split("`")
    .join("")
    .split(">")
    .join("")
    .split("-")
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}
