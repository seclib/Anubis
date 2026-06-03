import {
  Archive,
  BookOpen,
  Bot,
  Brain,
  Check,
  ChevronRight,
  Command,
  FileText,
  Folder,
  Library,
  Menu,
  MessageCircle,
  MoreHorizontal,
  Paperclip,
  PanelRight,
  Plus,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  Star,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, KeyboardEvent, TouchEvent, useEffect, useMemo, useRef, useState, WheelEvent } from "react";
import "./ui/styles.css";

type View = "chat" | "chats" | "projects" | "notes" | "files" | "settings";
type OverlayView = Exclude<View, "chat"> | "context";
type Role = "user" | "assistant";
type ResponseMode = "short" | "deep" | "builder";

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

type ProjectFolder = {
  id: string;
  name: string;
  summary: string;
  persistentMemory: string;
  conversations: Array<{ id: string; title: string; updatedAt: string; favorite: boolean }>;
  autoNotes: Array<{ id: string; title: string; excerpt: string }>;
  linkedFiles: Array<{ id: string; path: string; optional: boolean }>;
  tags: string[];
  favorite: boolean;
};

type FavoriteItem = {
  id: string;
  source: "conversation" | "message";
  title: string;
  excerpt: string;
  projectId: string;
};

const starterNotes: Note[] = [
  {
    id: "home",
    title: "Launch Brief",
    updatedAt: "Just now",
    body:
      "# Launch Brief\n\nAnubis should feel like a calm AI workspace: chat first, context aware, and premium. Execution details stay behind the product experience.",
  },
  {
    id: "ideas",
    title: "Product Ideas",
    updatedAt: "Today",
    body:
      "# Product Ideas\n\n- Mobile-first density on desktop\n- One primary conversation surface\n- Quiet workspace context\n- Agent activity shown as refined product status",
  },
  {
    id: "draft",
    title: "UX Notes",
    updatedAt: "Yesterday",
    body:
      "# UX Notes\n\nThe desktop app should borrow the intimacy of a phone chat while still giving power users fast access to files, vault search, git state, and settings.",
  },
];

const initialConversation: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "I am ready. Tell me what you want to build, review, or understand, and I will keep the workspace context close without exposing execution noise.",
  },
];

const starterProjects: ProjectFolder[] = [
  {
    id: "anubis-ui",
    name: "Anubis Desktop UI",
    summary: "Interface chat-first avec navigation mobile-like, contextes projet et experience premium.",
    persistentMemory:
      "L'utilisateur veut une app desktop IA qui ressemble a une app mobile haut de gamme. Les details techniques doivent rester invisibles dans l'experience principale.",
    conversations: [
      { id: "conv-ui-1", title: "Refonte chat desktop", updatedAt: "Just now", favorite: true },
      { id: "conv-ui-2", title: "Sidebar mobile-like", updatedAt: "Today", favorite: false },
    ],
    autoNotes: [
      { id: "note-ui-1", title: "Principes UX", excerpt: "Chat central, overlays contextuels, actions rapides." },
      { id: "note-ui-2", title: "Contraintes visuelles", excerpt: "Experience simple, glassmorphism leger, cards sobres." },
    ],
    linkedFiles: [{ id: "file-ui-1", path: "src/app/App.tsx", optional: false }],
    tags: ["dev", "product", "research"],
    favorite: true,
  },
  {
    id: "pentest-lab",
    name: "Pentest Lab",
    summary: "Workspace isole pour hypotheses, traces et syntheses de recherche offensive autorisee.",
    persistentMemory:
      "Maintenir une separation stricte entre contexte pentest, notes de recherche et conversations de developpement produit.",
    conversations: [{ id: "conv-pentest-1", title: "Scope RAG securise", updatedAt: "Yesterday", favorite: false }],
    autoNotes: [{ id: "note-pentest-1", title: "Scope", excerpt: "Tags, fichiers et memoire sont confines au dossier actif." }],
    linkedFiles: [],
    tags: ["pentest", "research"],
    favorite: false,
  },
];

const PROJECTS_STORAGE_KEY = "anubis-project-folders";
const ACTIVE_PROJECT_STORAGE_KEY = "anubis-active-project";
const GLOBAL_MEMORY_STORAGE_KEY = "anubis-global-memory";
const FAVORITES_STORAGE_KEY = "anubis-favorite-messages";

const responseModes: Array<{ id: ResponseMode; label: string }> = [
  { id: "short", label: "Short" },
  { id: "deep", label: "Deep analysis" },
  { id: "builder", label: "Builder" },
];

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeOverlay, setActiveOverlay] = useState<OverlayView | null>(null);
  const [notes, setNotes] = useState<Note[]>(starterNotes);
  const [activeNoteId, setActiveNoteId] = useState(starterNotes[0].id);
  const [saveState, setSaveState] = useState<"Saved" | "Saving...">("Saved");
  const [searchQuery, setSearchQuery] = useState("");
  const [chatSessionId, setChatSessionId] = useState(() => crypto.randomUUID());
  const [projects, setProjects] = useState<ProjectFolder[]>(loadStoredProjects);
  const [activeProjectId, setActiveProjectId] = useState(loadStoredActiveProject);
  const [globalMemory, setGlobalMemory] = useState(loadStoredGlobalMemory);
  const [favoriteMessages, setFavoriteMessages] = useState<FavoriteItem[]>(loadStoredFavorites);

  const activeNote = notes.find((note) => note.id === activeNoteId) ?? notes[0];
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? projects[0];

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

  useEffect(() => {
    if (!projects.some((project) => project.id === activeProjectId)) {
      setActiveProjectId(projects[0]?.id ?? starterProjects[0].id);
    }
  }, [activeProjectId, projects]);

  useEffect(() => {
    window.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
    window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, activeProjectId);
  }, [activeProjectId]);

  useEffect(() => {
    window.localStorage.setItem(GLOBAL_MEMORY_STORAGE_KEY, globalMemory);
  }, [globalMemory]);

  useEffect(() => {
    window.localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(favoriteMessages));
  }, [favoriteMessages]);

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
    setActiveOverlay("projects");
  }

  function startNewConversation() {
    const nextConversation = {
      id: crypto.randomUUID(),
      title: `Conversation ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`,
      updatedAt: "Just now",
      favorite: false,
    };
    setProjects((currentProjects) =>
      currentProjects.map((project) =>
        project.id === activeProjectId
          ? {
              ...project,
              conversations: [nextConversation, ...project.conversations],
              summary: summarizeProject(project, nextConversation.title),
            }
          : project,
      ),
    );
    setChatSessionId(crypto.randomUUID());
    setActiveNoteId(notes[0]?.id ?? starterNotes[0].id);
    setSearchQuery("");
    setActiveOverlay(null);
    setSidebarOpen(false);
  }

  function createProject() {
    const nextProject: ProjectFolder = {
      id: crypto.randomUUID(),
      name: "Nouveau projet",
      summary: "Nouveau contexte IA isole. Les conversations, notes et souvenirs seront scopes a ce dossier.",
      persistentMemory: "Ajoutez ici les elements que l'IA doit retenir pour ce projet.",
      conversations: [],
      autoNotes: [{ id: crypto.randomUUID(), title: "Note automatique", excerpt: "Les notes generees apparaitront ici." }],
      linkedFiles: [],
      tags: ["research"],
      favorite: false,
    };
    setProjects((currentProjects) => [nextProject, ...currentProjects]);
    setActiveProjectId(nextProject.id);
  }

  function renameProject(projectId: string, name: string) {
    setProjects((currentProjects) =>
      currentProjects.map((project) => (project.id === projectId ? { ...project, name } : project)),
    );
  }

  function deleteProject(projectId: string) {
    setProjects((currentProjects) => {
      if (currentProjects.length === 1) {
        return currentProjects;
      }
      const nextProjects = currentProjects.filter((project) => project.id !== projectId);
      if (activeProjectId === projectId) {
        setActiveProjectId(nextProjects[0].id);
      }
      return nextProjects;
    });
  }

  function toggleProjectFavorite(projectId: string) {
    setProjects((currentProjects) =>
      currentProjects.map((project) =>
        project.id === projectId ? { ...project, favorite: !project.favorite } : project,
      ),
    );
  }

  function toggleConversationFavorite(projectId: string, conversationId: string) {
    setProjects((currentProjects) =>
      currentProjects.map((project) =>
        project.id === projectId
          ? {
              ...project,
              conversations: project.conversations.map((conversation) =>
                conversation.id === conversationId
                  ? { ...conversation, favorite: !conversation.favorite }
                  : conversation,
              ),
            }
          : project,
      ),
    );
  }

  function updateProjectMemory(projectId: string, persistentMemory: string) {
    setProjects((currentProjects) =>
      currentProjects.map((project) => (project.id === projectId ? { ...project, persistentMemory } : project)),
    );
  }

  function favoriteMessage(message: ChatMessage) {
    setFavoriteMessages((currentFavorites) => {
      const existing = currentFavorites.some((favorite) => favorite.id === message.id);
      if (existing) {
        return currentFavorites.filter((favorite) => favorite.id !== message.id);
      }
      return [
        {
          id: message.id,
          source: "message",
          title: message.role === "user" ? "Message utilisateur" : "Reponse Anubis",
          excerpt: message.content,
          projectId: activeProjectId,
        },
        ...currentFavorites,
      ];
    });
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#0b0f17] text-[#f8fafc]">
      <section
        className={`anubis-depth-layer flex h-screen min-h-0 items-center justify-center px-6 py-6 ${
          sidebarOpen ? "drawer-open" : activeOverlay ? "panel-open" : ""
        }`}
      >
        <ChatPhone
          sessionId={chatSessionId}
          project={activeProject}
          favoriteMessageIds={favoriteMessages.map((favorite) => favorite.id)}
          onOpenSidebar={() => setSidebarOpen(true)}
          onOpenContext={() => setActiveOverlay("context")}
          onFavoriteMessage={favoriteMessage}
        />
      </section>

      <Sidebar
        activeOverlay={activeOverlay}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onChangeOverlay={(nextOverlay) => {
          setActiveOverlay(nextOverlay);
          setSidebarOpen(false);
        }}
        onNewConversation={startNewConversation}
      />

      {activeOverlay && (
        <OverlayPanel
          activeOverlay={activeOverlay}
          onClose={() => setActiveOverlay(null)}
          content={
            activeOverlay === "context" ? (
              <ContextPanel project={activeProject} saveState={saveState} />
            ) : (
              <WorkspacePanel
                activeView={activeOverlay}
                note={activeNote}
                notes={notes}
                projects={projects}
                activeProjectId={activeProjectId}
                globalMemory={globalMemory}
                favoriteMessages={favoriteMessages}
                saveState={saveState}
                searchQuery={searchQuery}
                onChangeNote={updateActiveNote}
                onChangeSearch={setSearchQuery}
                onChangeGlobalMemory={setGlobalMemory}
                onCreateProject={createProject}
                onDeleteProject={deleteProject}
                onRenameProject={renameProject}
                onSelectProject={setActiveProjectId}
                onToggleConversationFavorite={toggleConversationFavorite}
                onToggleProjectFavorite={toggleProjectFavorite}
                onUpdateProjectMemory={updateProjectMemory}
                onSelectNote={(noteId) => {
                  setActiveNoteId(noteId);
                  setActiveOverlay(null);
                }}
                onCreateNote={createNote}
              />
            )
          }
        />
      )}
    </main>
  );
}

function Sidebar({
  activeOverlay,
  open,
  onClose,
  onChangeOverlay,
  onNewConversation,
}: {
  activeOverlay: OverlayView | null;
  open: boolean;
  onClose: () => void;
  onChangeOverlay: (view: OverlayView | null) => void;
  onNewConversation: () => void;
}) {
  const touchStartX = useRef<number | null>(null);
  const items: Array<{ id: OverlayView | null; label: string; icon: typeof MessageCircle }> = [
    { id: null, label: "Chat", icon: MessageCircle },
    { id: "chats", label: "Chats", icon: MessageCircle },
    { id: "projects", label: "Projects", icon: Library },
    { id: "notes", label: "Notes", icon: BookOpen },
    { id: "files", label: "Files", icon: FileText },
    { id: "settings", label: "Settings", icon: Settings },
  ];

  function handleWheel(event: WheelEvent<HTMLElement>) {
    if (Math.abs(event.deltaX) > 48 && Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      onClose();
    }
  }

  function handleTouchStart(event: TouchEvent<HTMLElement>) {
    touchStartX.current = event.touches[0]?.clientX ?? null;
  }

  function handleTouchMove(event: TouchEvent<HTMLElement>) {
    const startX = touchStartX.current;
    const currentX = event.touches[0]?.clientX;
    if (startX === null || currentX === undefined) {
      return;
    }

    if (startX - currentX > 52) {
      touchStartX.current = null;
      onClose();
    }
  }

  return (
    <>
      <div
        className={`fixed inset-0 z-30 bg-[#020617]/18 backdrop-blur-md transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={`anubis-drawer fixed left-4 top-4 z-40 flex h-[calc(100vh-32px)] w-[292px] flex-col rounded-2xl border border-white/10 bg-[#111827]/78 px-4 py-5 shadow-[0_24px_80px_rgba(0,0,0,0.38)] backdrop-blur-2xl ${
          open ? "translate-x-0" : "closed -translate-x-[328px]"
        }`}
        aria-label="Navigation"
        onWheel={handleWheel}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
      >
        <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-white/10" aria-hidden="true" />
        <button
          type="button"
          onClick={onClose}
          className="absolute -right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-[#111827]/85 text-[#cbd5e1] shadow-[0_12px_40px_rgba(0,0,0,0.22)] backdrop-blur-xl transition hover:bg-[#1f2937]"
          aria-label="Close menu"
          title="Close"
        >
          <X size={16} />
        </button>

        <div className="flex items-center gap-3 px-1">
          <button
            type="button"
            onClick={() => onChangeOverlay(null)}
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#7c3aed] text-[#f8fafc] shadow-[0_12px_40px_rgba(0,0,0,0.22)] transition hover:bg-[#6d5dfc]"
            aria-label="Open chat"
            title="Anubis"
          >
            <ShieldCheck size={22} />
          </button>
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold tracking-tight text-[#f8fafc]">Anubis</h2>
            <p className="truncate text-xs text-[#94a3b8]">Menu principal</p>
          </div>
        </div>

        <button
          type="button"
          onClick={onNewConversation}
          className="mt-6 flex h-12 w-full items-center gap-3 rounded-2xl bg-[#7c3aed] px-4 text-left text-sm font-semibold text-[#f8fafc] shadow-[0_12px_40px_rgba(0,0,0,0.22)] transition hover:bg-[#6d5dfc]"
        >
          <Plus size={19} />
          Nouvelle conversation
        </button>

        <nav className="mt-6 flex flex-1 flex-col gap-2" aria-label="Primary">
          {items.map((item) => {
            const Icon = item.icon;
            const active = activeOverlay === item.id || (item.id === null && activeOverlay === null);
            return (
              <button
                key={item.label}
                type="button"
                onClick={() => onChangeOverlay(item.id)}
                className={`flex h-11 w-full items-center gap-3 rounded-2xl px-3 text-left text-sm transition ${
                  active
                    ? "bg-[#1e293b] text-[#f8fafc]"
                    : "text-[#94a3b8] hover:bg-[#1f2937] hover:text-[#f8fafc] active:scale-[0.98]"
                }`}
                aria-label={item.label}
                title={item.label}
              >
                <Icon size={20} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
    </>
  );
}

function OverlayPanel({
  activeOverlay,
  content,
  onClose,
}: {
  activeOverlay: OverlayView;
  content: React.ReactNode;
  onClose: () => void;
}) {
  const wide = activeOverlay === "projects";
  const touchStartX = useRef<number | null>(null);

  function handleTouchStart(event: TouchEvent<HTMLElement>) {
    touchStartX.current = event.touches[0]?.clientX ?? null;
  }

  function handleTouchMove(event: TouchEvent<HTMLElement>) {
    const startX = touchStartX.current;
    const currentX = event.touches[0]?.clientX;
    if (startX === null || currentX === undefined) {
      return;
    }

    if (currentX - startX > 64) {
      touchStartX.current = null;
      onClose();
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-[#020617]/18 backdrop-blur-[2px] transition-opacity">
      <button type="button" className="absolute inset-0 cursor-default" onClick={onClose} aria-label="Close panel" />
      <section
        className={`anubis-panel relative z-10 h-full overflow-hidden border-l border-white/10 bg-[#111827]/92 shadow-[0_30px_90px_rgba(0,0,0,0.38)] backdrop-blur-2xl ${
          wide ? "w-[min(1180px,calc(100vw-96px))]" : "w-[min(560px,calc(100vw-96px))]"
        }`}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 z-20 flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#cbd5e1] shadow-[0_12px_40px_rgba(0,0,0,0.22)] transition hover:bg-[#0b0f17] active:scale-95"
          aria-label="Close panel"
          title="Close"
        >
          <X size={18} />
        </button>
        {content}
      </section>
    </div>
  );
}

function WorkspacePanel({
  activeView,
  note,
  notes,
  projects,
  activeProjectId,
  globalMemory,
  favoriteMessages,
  saveState,
  searchQuery,
  onChangeNote,
  onChangeSearch,
  onChangeGlobalMemory,
  onCreateProject,
  onDeleteProject,
  onRenameProject,
  onSelectProject,
  onToggleConversationFavorite,
  onToggleProjectFavorite,
  onUpdateProjectMemory,
  onSelectNote,
  onCreateNote,
}: {
  activeView: View;
  note: Note;
  notes: Note[];
  projects: ProjectFolder[];
  activeProjectId: string;
  globalMemory: string;
  favoriteMessages: FavoriteItem[];
  saveState: "Saved" | "Saving...";
  searchQuery: string;
  onChangeNote: (body: string) => void;
  onChangeSearch: (query: string) => void;
  onChangeGlobalMemory: (value: string) => void;
  onCreateProject: () => void;
  onDeleteProject: (projectId: string) => void;
  onRenameProject: (projectId: string, name: string) => void;
  onSelectProject: (projectId: string) => void;
  onToggleConversationFavorite: (projectId: string, conversationId: string) => void;
  onToggleProjectFavorite: (projectId: string) => void;
  onUpdateProjectMemory: (projectId: string, memory: string) => void;
  onSelectNote: (noteId: string) => void;
  onCreateNote: () => void;
}) {
  if (activeView === "chats") {
    return (
      <ChatsView
        projects={projects}
        activeProjectId={activeProjectId}
        favoriteMessages={favoriteMessages}
        onSelectProject={onSelectProject}
        onToggleConversationFavorite={onToggleConversationFavorite}
      />
    );
  }

  if (activeView === "notes") {
    return (
      <NotesView
        notes={notes}
        query={searchQuery}
        onChangeQuery={onChangeSearch}
        onSelectNote={onSelectNote}
      />
    );
  }

  if (activeView === "files") {
    return <FilesView projects={projects} activeProjectId={activeProjectId} onSelectProject={onSelectProject} />;
  }

  if (activeView === "settings") {
    return <SettingsView />;
  }

  if (activeView === "projects") {
    return (
      <ProjectsView
        projects={projects}
        activeProjectId={activeProjectId}
        globalMemory={globalMemory}
        favoriteMessages={favoriteMessages}
        onChangeGlobalMemory={onChangeGlobalMemory}
        onCreateProject={onCreateProject}
        onDeleteProject={onDeleteProject}
        onRenameProject={onRenameProject}
        onSelectProject={onSelectProject}
        onToggleConversationFavorite={onToggleConversationFavorite}
        onToggleProjectFavorite={onToggleProjectFavorite}
        onUpdateProjectMemory={onUpdateProjectMemory}
      />
    );
  }

  return <SessionBrief note={note} notes={notes} onSelectNote={onSelectNote} />;
}

function SessionBrief({ note, notes, onSelectNote }: { note: Note; notes: Note[]; onSelectNote: (noteId: string) => void }) {
  return (
    <section className="min-h-0 overflow-auto border-r border-[#263241] bg-[#0f172a] px-6 py-6">
      <PanelHeader eyebrow="Workspace" title="Today" action={<Command size={18} />} />

      <div className="mt-7 rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#908b80]">Current note</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[#7c3aed]">{note.title}</h2>
          </div>
          <span className="rounded-full bg-[#12342f] px-3 py-1 text-xs font-medium text-[#22d3ee]">Active</span>
        </div>
        <p className="mt-4 line-clamp-5 text-sm leading-6 text-[#6f6b62]">{plainPreview(note.body)}</p>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <Metric label="Messages" value="Live" />
        <Metric label="Context" value={`${notes.length} docs`} />
      </div>

      <section className="mt-7">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#f8fafc]">Recent notes</h3>
          <MoreHorizontal size={18} className="text-[#94a3b8]" />
        </div>
        <div className="space-y-2">
          {notes.slice(0, 5).map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => onSelectNote(item.id)}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-[#1f2937]"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#94a3b8]">
                <FileText size={17} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-[#f8fafc]">{item.title}</span>
                <span className="block truncate text-xs text-[#94a3b8]">{item.updatedAt}</span>
              </span>
              <ChevronRight size={16} className="text-[#aaa59a]" />
            </button>
          ))}
        </div>
      </section>
    </section>
  );
}

function ProjectsView({
  projects,
  activeProjectId,
  globalMemory,
  favoriteMessages,
  onChangeGlobalMemory,
  onCreateProject,
  onDeleteProject,
  onRenameProject,
  onSelectProject,
  onToggleConversationFavorite,
  onToggleProjectFavorite,
  onUpdateProjectMemory,
}: {
  projects: ProjectFolder[];
  activeProjectId: string;
  globalMemory: string;
  favoriteMessages: FavoriteItem[];
  onChangeGlobalMemory: (value: string) => void;
  onCreateProject: () => void;
  onDeleteProject: (projectId: string) => void;
  onRenameProject: (projectId: string, name: string) => void;
  onSelectProject: (projectId: string) => void;
  onToggleConversationFavorite: (projectId: string, conversationId: string) => void;
  onToggleProjectFavorite: (projectId: string) => void;
  onUpdateProjectMemory: (projectId: string, memory: string) => void;
}) {
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? projects[0];
  const projectFavorites: FavoriteItem[] = projects.flatMap((project) =>
    project.conversations
      .filter((conversation) => conversation.favorite)
      .map((conversation) => ({
        id: conversation.id,
        source: "conversation" as const,
        title: conversation.title,
        excerpt: `Conversation liee a ${project.name}`,
        projectId: project.id,
      })),
  );
  const visibleFavorites = [...projectFavorites, ...favoriteMessages].filter((favorite) =>
    projects.some((project) => project.id === favorite.projectId),
  );

  return (
    <section className="grid h-full min-h-0 grid-cols-[320px_minmax(0,1fr)] overflow-hidden bg-[#0f172a]">
      <aside className="min-h-0 overflow-auto border-r border-[#263241] px-5 py-6">
        <PanelHeader
          eyebrow={`${projects.length} contextes isoles`}
          title="Projets"
          action={
            <button
              type="button"
              onClick={onCreateProject}
              className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#7c3aed] text-[#f8fafc]"
              aria-label="Creer un projet"
              title="Creer un projet"
            >
              <Plus size={18} />
            </button>
          }
        />

        <div className="mt-6 space-y-2">
          {projects.map((project) => (
            <button
              type="button"
              key={project.id}
              onClick={() => onSelectProject(project.id)}
              className={`w-full rounded-lg border p-4 text-left transition ${
                project.id === activeProjectId
                  ? "border-[#7c3aed] bg-[#111827]/88 shadow-[0_12px_40px_rgba(0,0,0,0.22)]"
                  : "border-[#263241] bg-[#111827] hover:border-[#334155]"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#172033] text-[#22d3ee]">
                  <Folder size={19} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-[#f8fafc]">{project.name}</span>
                    {project.favorite && <Star size={14} className="shrink-0 fill-[#facc15] text-[#facc15]" />}
                  </span>
                  <span className="mt-1 block line-clamp-2 text-xs leading-5 text-[#cbd5e1]">{project.summary}</span>
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {project.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-[#1e293b] px-2 py-0.5 text-[11px] text-[#67e8f9]">
                    {tag}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </aside>

      <div className="min-h-0 overflow-auto px-6 py-6">
        <div className="flex items-start justify-between gap-4 pr-14">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#818cf8]">RAG scoped memory</p>
            <input
              value={activeProject.name}
              onChange={(event) => onRenameProject(activeProject.id, event.target.value)}
              className="mt-1 w-full bg-transparent text-3xl font-semibold tracking-tight text-[#f8fafc] outline-none"
              aria-label="Nom du projet"
            />
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => onToggleProjectFavorite(activeProject.id)}
              className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#cbd5e1] shadow-[0_12px_40px_rgba(0,0,0,0.22)]"
              aria-label="Favori projet"
              title="Favori"
            >
              <Star size={18} className={activeProject.favorite ? "fill-[#facc15] text-[#facc15]" : ""} />
            </button>
            <button
              type="button"
              onClick={() => onDeleteProject(activeProject.id)}
              className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#fca5a5] shadow-[0_12px_40px_rgba(0,0,0,0.22)]"
              aria-label="Supprimer projet"
              title="Supprimer"
            >
              <Trash2 size={18} />
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-4">
            <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
                <Sparkles size={17} />
                Resume automatique
              </div>
              <p className="text-sm leading-6 text-[#cbd5e1]">{activeProject.summary}</p>
            </section>

            <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
                <Brain size={17} />
                Memoire IA persistante
              </div>
              <textarea
                value={activeProject.persistentMemory}
                onChange={(event) => onUpdateProjectMemory(activeProject.id, event.target.value)}
                className="min-h-[132px] w-full resize-none rounded-lg border border-[#263241] bg-[#111827] px-4 py-3 text-sm leading-6 text-[#f8fafc] outline-none focus:border-[#22d3ee]"
              />
            </section>

            <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
                <MessageCircle size={17} />
                Conversations liees
              </div>
              <div className="space-y-2">
                {activeProject.conversations.map((conversation) => (
                  <div key={conversation.id} className="flex items-center gap-3 rounded-lg bg-[#182033] px-3 py-3">
                    <button
                      type="button"
                      onClick={() => onToggleConversationFavorite(activeProject.id, conversation.id)}
                      className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#94a3b8]"
                      aria-label="Favori conversation"
                    >
                      <Star size={16} className={conversation.favorite ? "fill-[#facc15] text-[#facc15]" : ""} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-[#f8fafc]">{conversation.title}</p>
                      <p className="text-xs text-[#94a3b8]">{conversation.updatedAt}</p>
                    </div>
                  </div>
                ))}
                {activeProject.conversations.length === 0 && (
                  <p className="rounded-lg bg-[#182033] px-3 py-3 text-sm text-[#cbd5e1]">
                    Aucune conversation liee pour ce dossier.
                  </p>
                )}
              </div>
            </section>
          </div>

          <aside className="space-y-4">
            <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
                <Star size={17} />
                Favoris
              </div>
              <div className="space-y-2">
                {visibleFavorites.map((favorite) => (
                  <div key={`${favorite.source}-${favorite.id}`} className="rounded-lg bg-[#182033] px-3 py-3">
                    <p className="truncate text-sm font-medium text-[#f8fafc]">{favorite.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#cbd5e1]">{favorite.excerpt}</p>
                  </div>
                ))}
                {visibleFavorites.length === 0 && <p className="text-sm text-[#cbd5e1]">Aucun favori pour le moment.</p>}
              </div>
            </section>

            <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
                <FileText size={17} />
                Notes auto
              </div>
              <div className="space-y-2">
                {activeProject.autoNotes.map((autoNote) => (
                  <div key={autoNote.id} className="rounded-lg bg-[#182033] px-3 py-3">
                    <p className="text-sm font-medium text-[#f8fafc]">{autoNote.title}</p>
                    <p className="mt-1 text-xs leading-5 text-[#cbd5e1]">{autoNote.excerpt}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
                <Tag size={17} />
                Tags & fichiers
              </div>
              <div className="flex flex-wrap gap-2">
                {activeProject.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-[#1e293b] px-3 py-1 text-xs font-medium text-[#67e8f9]">
                    {tag}
                  </span>
                ))}
              </div>
              <div className="mt-4 space-y-2">
                {activeProject.linkedFiles.map((file) => (
                  <p key={file.id} className="truncate rounded-lg bg-[#182033] px-3 py-2 font-mono text-xs text-[#59645f]">
                    {file.path}
                  </p>
                ))}
                {activeProject.linkedFiles.length === 0 && <p className="text-sm text-[#cbd5e1]">Fichiers optionnels.</p>}
              </div>
            </section>
          </aside>
        </div>

        <section className="mt-4 rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
            <Brain size={17} />
            Memoire globale
          </div>
          <textarea
            value={globalMemory}
            onChange={(event) => onChangeGlobalMemory(event.target.value)}
            className="min-h-[118px] w-full resize-none rounded-lg border border-[#263241] bg-[#111827] px-4 py-3 text-sm leading-6 text-[#f8fafc] outline-none focus:border-[#22d3ee]"
          />
        </section>
      </div>
    </section>
  );
}

function FavoritesView({
  projects,
  favoriteMessages,
  onSelectProject,
  onToggleConversationFavorite,
}: {
  projects: ProjectFolder[];
  favoriteMessages: FavoriteItem[];
  onSelectProject: (projectId: string) => void;
  onToggleConversationFavorite: (projectId: string, conversationId: string) => void;
}) {
  const favoriteConversations = projects.flatMap((project) =>
    project.conversations
      .filter((conversation) => conversation.favorite)
      .map((conversation) => ({ ...conversation, project })),
  );

  return (
    <section className="h-full min-h-0 overflow-auto bg-[#0f172a] px-6 py-6">
      <PanelHeader eyebrow="Acces rapide" title="Favoris" action={<Star size={18} />} />

      <div className="mt-7 grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
            <MessageCircle size={17} />
            Conversations
          </div>
          <div className="space-y-2">
            {favoriteConversations.map((conversation) => (
              <div key={conversation.id} className="flex items-center gap-3 rounded-lg bg-[#182033] px-3 py-3">
                <button
                  type="button"
                  onClick={() => onToggleConversationFavorite(conversation.project.id, conversation.id)}
                  className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#facc15]"
                  aria-label="Retirer des favoris"
                  title="Retirer des favoris"
                >
                  <Star size={16} className="fill-[#facc15]" />
                </button>
                <button type="button" onClick={() => onSelectProject(conversation.project.id)} className="min-w-0 flex-1 text-left">
                  <p className="truncate text-sm font-medium text-[#f8fafc]">{conversation.title}</p>
                  <p className="truncate text-xs text-[#cbd5e1]">{conversation.project.name}</p>
                </button>
              </div>
            ))}
            {favoriteConversations.length === 0 && <p className="text-sm text-[#cbd5e1]">Aucune conversation starred.</p>}
          </div>
        </section>

        <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
            <Archive size={17} />
            Messages
          </div>
          <div className="space-y-2">
            {favoriteMessages.map((favorite) => {
              const project = projects.find((item) => item.id === favorite.projectId);
              return (
                <button
                  type="button"
                  key={favorite.id}
                  onClick={() => favorite.projectId && onSelectProject(favorite.projectId)}
                  className="w-full rounded-lg bg-[#182033] px-3 py-3 text-left"
                >
                  <p className="truncate text-sm font-medium text-[#f8fafc]">{favorite.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#cbd5e1]">{favorite.excerpt}</p>
                  <p className="mt-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[#818cf8]">
                    {project?.name ?? "Projet"}
                  </p>
                </button>
              );
            })}
            {favoriteMessages.length === 0 && <p className="text-sm text-[#cbd5e1]">Aucun message favori.</p>}
          </div>
        </section>
      </div>
    </section>
  );
}

function ChatsView({
  projects,
  activeProjectId,
  favoriteMessages,
  onSelectProject,
  onToggleConversationFavorite,
}: {
  projects: ProjectFolder[];
  activeProjectId: string;
  favoriteMessages: FavoriteItem[];
  onSelectProject: (projectId: string) => void;
  onToggleConversationFavorite: (projectId: string, conversationId: string) => void;
}) {
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? projects[0];
  const starredConversations = projects.flatMap((project) =>
    project.conversations
      .filter((conversation) => conversation.favorite)
      .map((conversation) => ({ ...conversation, project })),
  );

  return (
    <section className="h-full min-h-0 overflow-auto bg-[#0f172a] px-6 py-6">
      <PanelHeader eyebrow="Conversations" title="Chats" action={<MessageCircle size={18} />} />

      <div className="mt-7 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[#f8fafc]">{activeProject.name}</h3>
              <p className="text-xs text-[#94a3b8]">{activeProject.conversations.length} chats in this project</p>
            </div>
          </div>
          <div className="space-y-2">
            {activeProject.conversations.map((conversation) => (
              <div key={conversation.id} className="flex items-center gap-3 rounded-lg bg-[#182033] px-3 py-3">
                <button
                  type="button"
                  onClick={() => onToggleConversationFavorite(activeProject.id, conversation.id)}
                  className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#94a3b8]"
                  aria-label="Star chat"
                  title="Star chat"
                >
                  <Star size={16} className={conversation.favorite ? "fill-[#facc15] text-[#facc15]" : ""} />
                </button>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-[#f8fafc]">{conversation.title}</p>
                  <p className="text-xs text-[#94a3b8]">{conversation.updatedAt}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-lg border border-[#263241] bg-[#111827]/88 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
              <Star size={17} />
              Starred
            </div>
            <div className="space-y-2">
              {starredConversations.map((conversation) => (
                <button
                  type="button"
                  key={conversation.id}
                  onClick={() => onSelectProject(conversation.project.id)}
                  className="w-full rounded-lg bg-[#182033] px-3 py-3 text-left"
                >
                  <p className="truncate text-sm font-medium text-[#f8fafc]">{conversation.title}</p>
                  <p className="truncate text-xs text-[#94a3b8]">{conversation.project.name}</p>
                </button>
              ))}
              {favoriteMessages.slice(0, 4).map((favorite) => (
                <div key={favorite.id} className="rounded-lg bg-[#182033] px-3 py-3">
                  <p className="truncate text-sm font-medium text-[#f8fafc]">{favorite.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-[#cbd5e1]">{favorite.excerpt}</p>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}

function NotesView({
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

  const visibleNotes = query ? results : notes;

  return (
    <section className="min-h-0 overflow-auto border-r border-[#263241] bg-[#0f172a] px-6 py-6">
      <PanelHeader eyebrow="Knowledge base" title="Notes" action={<BookOpen size={18} />} />
      <label className="mt-6 flex h-12 items-center gap-3 rounded-lg border border-[#263241] bg-[#111827]/88 px-4 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
        <Search size={18} className="text-[#94a3b8]" />
        <input
          value={query}
          onChange={(event) => onChangeQuery(event.target.value)}
          className="min-w-0 flex-1 bg-transparent text-sm text-[#f8fafc] outline-none placeholder:text-[#64748b]"
          placeholder="Search knowledge..."
        />
      </label>

      <div className="mt-6 space-y-2">
        {visibleNotes.map((item) => (
          <button
            type="button"
            key={item.id}
            onClick={() => onSelectNote(item.id)}
            className="w-full rounded-lg border border-[#263241] bg-[#111827] p-4 text-left transition hover:border-[#334155]"
          >
            <h3 className="text-sm font-semibold text-[#f8fafc]">{item.title}</h3>
            <p className="mt-2 line-clamp-2 text-sm leading-6 text-[#cbd5e1]">{plainPreview(item.body)}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

function FilesView({
  projects,
  activeProjectId,
  onSelectProject,
}: {
  projects: ProjectFolder[];
  activeProjectId: string;
  onSelectProject: (projectId: string) => void;
}) {
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? projects[0];
  const files = projects.flatMap((project) => project.linkedFiles.map((file) => ({ ...file, project })));
  const visibleFiles = files.length
    ? files
    : activeProject.linkedFiles.map((file) => ({ ...file, project: activeProject }));

  return (
    <section className="h-full min-h-0 overflow-auto bg-[#0f172a] px-6 py-6">
      <PanelHeader eyebrow="Documents" title="Files" action={<Paperclip size={18} />} />
      <div className="mt-7 space-y-3">
        {visibleFiles.map((file) => {
          const project = file.project;
          return (
            <button
              type="button"
              key={file.id}
              onClick={() => onSelectProject(project.id)}
              className="flex w-full items-center gap-3 rounded-lg border border-[#263241] bg-[#111827]/88 px-4 py-4 text-left"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#1e293b] text-[#22d3ee]">
                <FileText size={18} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-sm text-[#f8fafc]">{file.path}</span>
                <span className="block text-xs text-[#94a3b8]">{project.name}</span>
              </span>
            </button>
          );
        })}
        {files.length === 0 && activeProject.linkedFiles.length === 0 && (
          <p className="rounded-lg border border-[#263241] bg-[#111827]/88 px-4 py-4 text-sm text-[#cbd5e1]">
            Attach files from the chat input to build document intelligence for this project.
          </p>
        )}
      </div>
    </section>
  );
}

function SettingsView() {
  return (
    <section className="min-h-0 overflow-auto border-r border-[#263241] bg-[#0f172a] px-6 py-6">
      <PanelHeader eyebrow="Preferences" title="Settings" action={<Settings size={18} />} />
      <div className="mt-7 space-y-3">
        <SettingRow title="Theme" value="Warm light" />
        <SettingRow title="Autosave" value="On" />
        <SettingRow title="Agent mode" value="Quiet execution" />
        <SettingRow title="Execution surface" value="Hidden" />
      </div>
    </section>
  );
}

function ChatPhone({
  sessionId,
  project,
  favoriteMessageIds,
  onOpenSidebar,
  onOpenContext,
  onFavoriteMessage,
}: {
  sessionId: string;
  project: ProjectFolder;
  favoriteMessageIds: string[];
  onOpenSidebar: () => void;
  onOpenContext: () => void;
  onFavoriteMessage: (message: ChatMessage) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialConversation);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [responseMode, setResponseMode] = useState<ResponseMode>("deep");
  const [inputClearing, setInputClearing] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottomRef = useRef(true);
  const touchStartX = useRef<number | null>(null);

  useEffect(() => {
    setMessages(initialConversation);
    setInput("");
    setLoading(false);
    stickToBottomRef.current = true;
  }, [sessionId, project.id]);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      if (scrollRef.current && stickToBottomRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [messages, loading]);

  useEffect(() => {
    const inputElement = inputRef.current;
    if (!inputElement) {
      return;
    }
    inputElement.style.height = "44px";
    inputElement.style.height = `${Math.min(inputElement.scrollHeight, 132)}px`;
  }, [input]);

  function handleScroll() {
    const scroller = scrollRef.current;
    if (!scroller) {
      return;
    }
    const distanceFromBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 80;
  }

  async function submitPrompt(prompt: string) {
    if (!prompt || loading) {
      return;
    }

    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: prompt,
      },
    ]);
    setInputClearing(true);
    window.setTimeout(() => {
      setInput("");
      setInputClearing(false);
    }, 120);
    setLoading(true);

    const answer = await askAssistant(prompt, project, responseMode);
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

  async function submitMessage(event?: FormEvent) {
    event?.preventDefault();
    const prompt = input.trim();
    await submitPrompt(prompt);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitMessage();
    }
  }

  function handleShellTouchStart(event: TouchEvent<HTMLElement>) {
    touchStartX.current = event.touches[0]?.clientX ?? null;
  }

  function handleShellTouchMove(event: TouchEvent<HTMLElement>) {
    const startX = touchStartX.current;
    const currentX = event.touches[0]?.clientX;
    if (startX === null || currentX === undefined) {
      return;
    }

    const deltaX = currentX - startX;
    if (deltaX > 72) {
      touchStartX.current = null;
      onOpenSidebar();
    }
    if (deltaX < -72) {
      touchStartX.current = null;
      onOpenContext();
    }
  }

  const projectPrompts = projectPromptSuggestions(project);

  return (
    <section
      className="flex h-full min-h-0 w-full items-center justify-center bg-[#0b0f17] px-7 py-6"
      onTouchStart={handleShellTouchStart}
      onTouchMove={handleShellTouchMove}
    >
      <div className="flex h-full max-h-[940px] w-full max-w-[700px] flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#111827]/88 shadow-[0_30px_80px_rgba(0,0,0,0.38)] backdrop-blur-xl">
        <header className="flex items-center justify-between border-b border-[#263241] px-5 py-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onOpenSidebar}
              className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#1e293b] text-[#cbd5e1] transition active:scale-95"
              aria-label="Open menu"
              title="Menu"
            >
              <Menu size={19} />
            </button>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-[#f8fafc]">Anubis</h1>
              <p className="text-xs text-[#94a3b8]">{project.name}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onOpenContext}
            className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#7c3aed] text-[#f8fafc] transition active:scale-95"
            aria-label="Open context"
            title="Context"
          >
            <Bot size={19} />
          </button>
        </header>

        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="momentum-scroll min-h-0 flex-1 space-y-4 overflow-auto px-4 py-5"
        >
          <div className="mx-auto mb-2 flex w-fit items-center gap-2 rounded-full bg-[#172033] px-3 py-1 text-xs text-[#22d3ee]">
            <Sparkles size={13} />
            Contexte isole: {project.name}
          </div>
          <div className="mx-auto mb-4 flex w-fit gap-2">
            <button
              type="button"
              onClick={() => submitPrompt("Resume ce projet.")}
              className="rounded-full bg-[#111827]/88 px-3 py-1.5 text-xs font-medium text-[#22d3ee] shadow-[0_12px_40px_rgba(0,0,0,0.22)] transition hover:bg-[#0f172a] active:scale-95"
            >
              Resume
            </button>
            <button
              type="button"
              onClick={() => submitPrompt("Propose des insights lies a ce projet.")}
              className="rounded-full bg-[#111827]/88 px-3 py-1.5 text-xs font-medium text-[#22d3ee] shadow-[0_12px_40px_rgba(0,0,0,0.22)] transition hover:bg-[#0f172a] active:scale-95"
            >
              Insights
            </button>
          </div>
          <section className="anubis-card-settle rounded-2xl border border-white/10 bg-[#0f172a]/72 p-4 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#1e293b] text-[#22d3ee]">
                <Brain size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-[#f8fafc]">Workspace intelligent</p>
                <p className="mt-1 line-clamp-3 text-xs leading-5 text-[#cbd5e1]">{project.summary}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {project.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-[#1e293b] px-2.5 py-1 text-[11px] font-medium text-[#67e8f9]">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </section>
          <div className="momentum-scroll flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {projectPrompts.map((suggestion) => (
              <button
                type="button"
                key={suggestion}
                onClick={() => submitPrompt(suggestion)}
                className="shrink-0 rounded-2xl border border-white/10 bg-[#111827]/88 px-3 py-2 text-left text-xs leading-5 text-[#cbd5e1] transition hover:border-[#22d3ee]/40 hover:text-[#f8fafc] active:scale-[0.98]"
              >
                {suggestion}
              </button>
            ))}
          </div>
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              favorite={favoriteMessageIds.includes(message.id)}
              onFavorite={() => onFavoriteMessage(message)}
            />
          ))}
          {loading && (
            <div className="mr-auto flex max-w-[86%] items-center gap-2 rounded-2xl rounded-bl-lg bg-[#172033] px-4 py-3">
              <span className="anubis-typing-dot h-2 w-2 rounded-full bg-[#22d3ee]" />
              <span className="anubis-typing-dot h-2 w-2 rounded-full bg-[#818cf8]" />
              <span className="anubis-typing-dot h-2 w-2 rounded-full bg-[#c4b5fd]" />
            </div>
          )}
        </div>

        <form onSubmit={submitMessage} className="border-t border-[#263241] bg-[#111827] p-4">
          <div className="momentum-scroll mb-3 flex gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {responseModes.map((mode) => (
              <button
                type="button"
                key={mode.id}
                onClick={() => setResponseMode(mode.id)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  responseMode === mode.id
                    ? "bg-[#7c3aed] text-[#f8fafc]"
                    : "bg-[#0f172a] text-[#94a3b8] hover:text-[#f8fafc]"
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <div className={`anubis-composer flex items-end gap-2 rounded-lg border border-[#263241] bg-[#111827]/88 p-2 shadow-[0_12px_40px_rgba(0,0,0,0.22)] ${loading ? "sending" : ""}`}>
            <button
              type="button"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#0f172a] text-[#94a3b8] transition hover:text-[#f8fafc] active:scale-95"
              aria-label="Attach files"
              title="Attach"
            >
              <Paperclip size={18} />
            </button>
            <textarea
              ref={inputRef}
              value={input}
              disabled={loading}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              className={`max-h-32 min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-6 text-[#f8fafc] outline-none placeholder:text-[#64748b] transition-opacity duration-[120ms] ${inputClearing ? "opacity-0" : "opacity-100"}`}
              placeholder={loading ? "Anubis is responding..." : "Message Anubis"}
            />
            <button
              type={loading ? "button" : "submit"}
              disabled={!loading && !input.trim()}
              onClick={loading ? () => setLoading(false) : undefined}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#7c3aed] text-[#f8fafc] transition hover:bg-[#6d5dfc] disabled:cursor-not-allowed disabled:bg-[#334155]"
              aria-label={loading ? "Stop response" : "Send message"}
              title={loading ? "Stop" : "Send"}
            >
              {loading ? <Square size={16} /> : <Send size={18} />}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

function MessageBubble({
  message,
  favorite,
  onFavorite,
}: {
  message: ChatMessage;
  favorite: boolean;
  onFavorite: () => void;
}) {
  const user = message.role === "user";

  return (
    <article className={`anubis-message group flex max-w-[86%] items-start gap-2 ${user ? "ml-auto flex-row-reverse" : "mr-auto"}`}>
      <div
        className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
          user
            ? "rounded-br-lg bg-[#7c3aed] text-[#f8fafc]"
            : "rounded-bl-lg bg-[#172033] text-[#e5e7eb]"
        }`}
      >
        <MessageContent content={message.content} />
      </div>
      <button
        type="button"
        onClick={onFavorite}
        className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-[#111827]/85 text-[#94a3b8] shadow-[0_12px_40px_rgba(0,0,0,0.22)] transition group-hover:opacity-100 ${
          favorite ? "opacity-100" : "opacity-0"
        }`}
        aria-label="Favori message"
        title="Favori"
      >
        <Star size={15} className={favorite ? "fill-[#facc15] text-[#facc15]" : ""} />
      </button>
    </article>
  );
}

function MessageContent({ content }: { content: string }) {
  return (
    <>
      {splitCodeFences(content).map((block, index) =>
        block.type === "code" ? (
          <pre
            key={`${block.type}-${index}`}
            className="my-2 max-w-full overflow-auto rounded-lg border border-[#334155] bg-[#020617] px-3 py-3 font-mono text-[12px] leading-5 text-[#e2e8f0]"
          >
            <code>{block.content}</code>
          </pre>
        ) : (
          <StructuredText key={`${block.type}-${index}`} content={block.content} />
        ),
      )}
    </>
  );
}

function StructuredText({ content }: { content: string }) {
  return (
    <div className="space-y-2">
      {content
        .split("\n")
        .filter((line) => line.trim().length > 0)
        .map((line, index) => {
          const trimmed = line.trim();
          if (trimmed.startsWith("## ")) {
            return (
              <h3
                key={`${trimmed}-${index}`}
                className="anubis-chunk pt-1 text-[15px] font-semibold text-[#f8fafc]"
                style={{ animationDelay: `${Math.min(index * 35, 180)}ms` }}
              >
                {trimmed.replace(/^##\s*/, "")}
              </h3>
            );
          }
          if (trimmed.startsWith("### ")) {
            return (
              <h4
                key={`${trimmed}-${index}`}
                className="anubis-chunk text-[13px] font-semibold text-[#c4b5fd]"
                style={{ animationDelay: `${Math.min(index * 35, 180)}ms` }}
              >
                {trimmed.replace(/^###\s*/, "")}
              </h4>
            );
          }
          if (trimmed.startsWith("- ")) {
            return (
              <p
                key={`${trimmed}-${index}`}
                className="anubis-chunk pl-3 text-sm leading-6 text-[#e5e7eb]"
                style={{ animationDelay: `${Math.min(index * 35, 180)}ms` }}
              >
                <span className="mr-2 text-[#22d3ee]">•</span>
                {trimmed.replace(/^-\s*/, "")}
              </p>
            );
          }
          return (
            <p
              key={`${trimmed}-${index}`}
              className="anubis-chunk text-sm leading-6"
              style={{ animationDelay: `${Math.min(index * 35, 180)}ms` }}
            >
              {trimmed}
            </p>
          );
        })}
    </div>
  );
}

function ContextPanel({ project, saveState }: { project: ProjectFolder; saveState: "Saved" | "Saving..." }) {
  const keywords = useMemo(
    () => extractKeywords(`${project.name} ${project.summary} ${project.persistentMemory} ${project.tags.join(" ")}`),
    [project],
  );

  return (
    <aside className="min-h-0 overflow-auto border-l border-[#263241] bg-[#111827] px-6 py-6">
      <PanelHeader eyebrow="Agent state" title="Context" action={<PanelRight size={18} />} />

      <div className="mt-7 rounded-lg border border-[#263241] bg-[#111827]/88 p-5 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#12342f] text-[#22d3ee]">
            <ShieldCheck size={20} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[#f8fafc]">Isolation projet active</h2>
            <p className="text-xs text-[#837d73]">L'IA ne lit que ce workspace.</p>
          </div>
        </div>
        <div className="mt-5 space-y-3">
          <StatusRow label="Projet" value={project.name} />
          <StatusRow label="Conversations" value={`${project.conversations.length}`} />
          <StatusRow label="Memoire RAG" value="Scoped" />
          <StatusRow label="Autosave" value={saveState} />
        </div>
      </div>

      <section className="mt-6 rounded-lg border border-[#263241] bg-[#111827]/88 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
          <Archive size={17} />
          Resume automatique
        </div>
        <h3 className="mt-4 text-xl font-semibold tracking-tight text-[#f8fafc]">{project.name}</h3>
        <p className="mt-3 text-sm leading-6 text-[#cbd5e1]">{project.summary}</p>
      </section>

      <section className="mt-6 rounded-lg border border-[#263241] bg-[#111827]/88 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#f8fafc]">
          <Brain size={17} />
          Memoire IA lue
        </div>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[#cbd5e1]">{project.persistentMemory}</p>
      </section>

      <section className="mt-6">
        <h3 className="text-sm font-semibold text-[#f8fafc]">Keywords</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {keywords.map((keyword) => (
            <span key={keyword} className="rounded-full bg-[#1e293b] px-3 py-1 text-xs font-medium text-[#67e8f9]">
              {keyword}
            </span>
          ))}
        </div>
      </section>
    </aside>
  );
}

function PanelHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#818cf8]">{eyebrow}</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#f8fafc]">{title}</h2>
      </div>
      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#111827]/88 text-[#cbd5e1] shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
        {action}
      </span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#263241] bg-[#111827] p-4">
      <p className="text-xs text-[#94a3b8]">{label}</p>
      <p className="mt-2 text-lg font-semibold text-[#f8fafc]">{value}</p>
    </div>
  );
}

function SettingRow({ title, value }: { title: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-[#263241] bg-[#111827]/88 px-4 py-4">
      <span className="text-sm font-medium text-[#f8fafc]">{title}</span>
      <span className="text-sm text-[#94a3b8]">{value}</span>
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-[#1f2937] pt-3 text-sm">
      <span className="text-[#94a3b8]">{label}</span>
      <span className="font-medium text-[#f8fafc]">{value}</span>
    </div>
  );
}

async function askAssistant(prompt: string, project: ProjectFolder, mode: ResponseMode): Promise<string> {
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: prompt,
        project: {
          id: project.id,
          name: project.name,
          summary: project.summary,
          memory: project.persistentMemory,
          tags: project.tags,
          conversations: project.conversations.map((conversation) => ({
            id: conversation.id,
            title: conversation.title,
            favorite: conversation.favorite,
          })),
          notes: project.autoNotes,
          files: project.linkedFiles,
        },
        isolation: "project-only",
        mode,
      }),
    });

    if (response.ok) {
      const data = (await response.json()) as { answer?: string; message?: string };
      return data.answer ?? data.message ?? mockAnswer(prompt, project, mode);
    }
  } catch {
    return mockAnswer(prompt, project, mode);
  }

  return mockAnswer(prompt, project, mode);
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

function mockAnswer(prompt: string, project: ProjectFolder, mode: ResponseMode): string {
  const lowerPrompt = prompt.toLowerCase();

  if (mode === "short") {
    return `## Short answer\n${project.summary}`;
  }

  if (mode === "builder") {
    return `## Builder mode\n\n### Architecture\n- Project context: ${project.name}\n- Memory scope: isolated\n- Tags: ${project.tags.join(", ") || "general"}\n\n### Next build step\nTurn the current project memory into concrete actions and keep every answer scoped to this workspace.`;
  }

  if (lowerPrompt.includes("résum") || lowerPrompt.includes("resum") || lowerPrompt.includes("summar")) {
    return `## Résumé de ${project.name}\n\n${project.summary}\n\n### Mémoire utilisée\n${project.persistentMemory.slice(0, 220)}${project.persistentMemory.length > 220 ? "..." : ""}`;
  }

  if (lowerPrompt.includes("insight")) {
    return `## Insights liés à ${project.name}\n\n- Les tags dominants sont ${project.tags.join(", ") || "general"}.\n- ${project.conversations.length} conversation(s) alimentent ce contexte isolé.\n- Prochaine étape utile : transformer la mémoire persistante en décisions vérifiables.`;
  }

  return `## Réponse contextualisée\n\nJe réponds uniquement avec le contexte isolé du projet **${project.name}**.\n\n### Mémoire active\n${project.persistentMemory.slice(0, 180)}${project.persistentMemory.length > 180 ? "..." : ""}`;
}

function summarizeProject(project: ProjectFolder, latestConversationTitle: string): string {
  const tags = project.tags.length ? project.tags.join(", ") : "general";
  return `${project.name} regroupe ${project.conversations.length + 1} conversation(s) autour de ${tags}. Dernier focus: ${latestConversationTitle}.`;
}

function projectPromptSuggestions(project: ProjectFolder): string[] {
  const tags = new Set(project.tags);
  if (tags.has("pentest")) {
    return [
      "Resume le scope et les risques prioritaires.",
      "Liste les hypotheses a verifier dans ce projet.",
      "Transforme les notes en plan de recherche.",
    ];
  }

  if (tags.has("dev")) {
    return [
      "Propose la prochaine iteration produit.",
      "Resume les decisions techniques importantes.",
      "Liste les risques UX a surveiller.",
    ];
  }

  return [
    "Resume ce workspace en 5 points.",
    "Quels insights importants dois-je retenir ?",
    "Organise ce projet pour une longue session.",
  ];
}

function splitCodeFences(content: string): Array<{ type: "text" | "code"; content: string }> {
  const blocks: Array<{ type: "text" | "code"; content: string }> = [];
  const fencePattern = /```(?:\w+)?\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = fencePattern.exec(content))) {
    if (match.index > cursor) {
      blocks.push({ type: "text", content: content.slice(cursor, match.index) });
    }
    blocks.push({ type: "code", content: match[1].trimEnd() });
    cursor = match.index + match[0].length;
  }

  if (cursor < content.length) {
    blocks.push({ type: "text", content: content.slice(cursor) });
  }

  return blocks.length ? blocks : [{ type: "text", content }];
}

function loadStoredProjects(): ProjectFolder[] {
  const stored = window.localStorage.getItem(PROJECTS_STORAGE_KEY);
  if (!stored) {
    return starterProjects;
  }

  try {
    const parsed = JSON.parse(stored) as ProjectFolder[];
    return Array.isArray(parsed) && parsed.length ? parsed : starterProjects;
  } catch {
    return starterProjects;
  }
}

function loadStoredActiveProject(): string {
  return window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY) ?? starterProjects[0].id;
}

function loadStoredGlobalMemory(): string {
  return (
    window.localStorage.getItem(GLOBAL_MEMORY_STORAGE_KEY) ??
    "Anubis doit conserver les decisions produit importantes, separer les contextes par projet, et rendre la memoire editable par l'utilisateur."
  );
}

function loadStoredFavorites(): FavoriteItem[] {
  const stored = window.localStorage.getItem(FAVORITES_STORAGE_KEY);
  if (!stored) {
    return [];
  }

  try {
    const parsed = JSON.parse(stored) as FavoriteItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
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

function extractKeywords(markdown: string): string[] {
  const stopWords = new Set(["the", "and", "for", "with", "this", "that", "into", "should", "workspace"]);
  const counts = plainPreview(markdown)
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((word) => word.length > 3 && !stopWords.has(word))
    .reduce<Map<string, number>>((map, word) => map.set(word, (map.get(word) ?? 0) + 1), new Map());

  const keywords = [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 6)
    .map(([word]) => word);

  return keywords.length ? keywords : ["anubis", "context", "chat"];
}
