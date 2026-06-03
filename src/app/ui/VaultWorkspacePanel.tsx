import { FormEvent, useEffect, useMemo, useState } from "react";
import { BrainCircuit, FileText, GitBranch, Link2, Network, RefreshCw, Search } from "lucide-react";
import {
  readVaultNote,
  searchVault,
  vaultBacklinks,
  vaultSnapshot,
  writeVaultNote,
  type VaultBacklink,
  type VaultGraph,
  type VaultNote,
  type VaultSearchResult,
} from "../core/vaultWorkspace";

export function VaultWorkspacePanel() {
  const [notes, setNotes] = useState<VaultNote[]>([]);
  const [graph, setGraph] = useState<VaultGraph>({ nodes: [], edges: [] });
  const [activePath, setActivePath] = useState("");
  const [content, setContent] = useState("");
  const [backlinks, setBacklinks] = useState<VaultBacklink[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<VaultSearchResult[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const activeNote = notes.find((note) => note.path === activePath) ?? notes[0];
  const connectedEdges = useMemo(
    () => graph.edges.filter((edge) => edge.source === activePath || edge.target === activePath),
    [activePath, graph.edges],
  );

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!activeNote) {
      return;
    }
    loadNote(activeNote.path);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeNote?.path]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const snapshot = await vaultSnapshot();
      setNotes(snapshot.notes);
      setGraph(snapshot.graph);
      if (!activePath && snapshot.notes.length > 0) {
        setActivePath(snapshot.notes[0].path);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Vault unavailable");
    } finally {
      setLoading(false);
    }
  }

  async function loadNote(path: string) {
    setError("");
    try {
      const [note, noteBacklinks] = await Promise.all([readVaultNote(path), vaultBacklinks(path)]);
      setContent(note.content);
      setBacklinks(noteBacklinks);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load note");
    }
  }

  async function saveCurrentNote() {
    if (!activePath) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await writeVaultNote(activePath, content, true);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save note");
    } finally {
      setSaving(false);
    }
  }

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      setResults(await searchVault(query, 8));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed");
    }
  }

  return (
    <section className="grid min-h-0 grid-cols-[260px_minmax(0,1fr)_320px] bg-neutral-950">
      <aside className="min-h-0 overflow-auto border-r border-neutral-800 p-4">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-neutral-100">
            <FileText size={16} />
            Markdown
          </div>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="rounded border border-neutral-800 bg-neutral-900 p-2 text-neutral-300 transition hover:border-neutral-700 disabled:opacity-50"
            title="Refresh vault"
          >
            <RefreshCw size={14} />
          </button>
        </div>

        <div className="space-y-2">
          {notes.map((note) => (
            <button
              key={note.path}
              type="button"
              onClick={() => setActivePath(note.path)}
              className={`w-full rounded-lg border p-3 text-left transition ${
                activePath === note.path
                  ? "border-neutral-600 bg-neutral-800/80"
                  : "border-neutral-800 bg-neutral-900/40 hover:border-neutral-700"
              }`}
            >
              <p className="truncate text-sm font-medium text-neutral-100">{note.title}</p>
              <p className="mt-1 truncate font-mono text-[11px] text-neutral-500">{note.path}</p>
              {note.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {note.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="rounded border border-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
                      #{tag}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
          {notes.length === 0 && <p className="text-sm text-neutral-500">No markdown notes found.</p>}
        </div>
      </aside>

      <div className="flex min-h-0 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-neutral-800 px-6">
          <div>
            <h2 className="text-sm font-medium text-neutral-100">{activeNote?.title ?? "Vault"}</h2>
            <p className="font-mono text-xs text-neutral-500">{activePath || "Local-first markdown workspace"}</p>
          </div>
          <button
            type="button"
            onClick={saveCurrentNote}
            disabled={saving || !activePath}
            className="rounded bg-neutral-100 px-3 py-2 text-sm font-medium text-neutral-950 transition hover:bg-white disabled:opacity-50"
          >
            {saving ? "Saving" : "Save"}
          </button>
        </header>

        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          className="min-h-0 flex-1 resize-none bg-neutral-950 px-8 py-7 font-mono text-sm leading-7 text-neutral-200 outline-none placeholder:text-neutral-600"
          placeholder="Select a markdown note..."
          spellCheck="true"
        />
      </div>

      <aside className="min-h-0 overflow-auto border-l border-neutral-800 bg-[#0f0f0f] p-4">
        <form onSubmit={submitSearch} className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-neutral-200">
            <BrainCircuit size={15} />
            AI-assisted search
          </div>
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-9 min-w-0 flex-1 rounded border border-neutral-800 bg-neutral-950 px-3 text-sm text-neutral-100 outline-none focus:border-neutral-600"
              placeholder="Search vault memory"
            />
            <button className="rounded bg-neutral-100 px-3 text-neutral-950" type="submit" title="Search vault">
              <Search size={14} />
            </button>
          </div>
          <div className="mt-3 space-y-2">
            {results.map((result) => (
              <button
                type="button"
                key={`${result.source}:${result.path}`}
                onClick={() => setActivePath(result.path)}
                className="w-full rounded border border-neutral-800 bg-neutral-950 p-2 text-left hover:border-neutral-700"
              >
                <p className="truncate text-xs font-medium text-neutral-200">{result.title}</p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-neutral-500">{result.excerpt}</p>
                <p className="mt-1 text-[10px] uppercase text-neutral-600">{result.source}</p>
              </button>
            ))}
          </div>
        </form>

        <section className="mt-4 rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-neutral-200">
            <Link2 size={15} />
            Backlinks
          </div>
          <div className="space-y-2">
            {backlinks.map((backlink) => (
              <button
                key={`${backlink.source_path}:${backlink.line}`}
                type="button"
                onClick={() => setActivePath(backlink.source_path)}
                className="w-full rounded border border-neutral-800 bg-neutral-950 p-2 text-left hover:border-neutral-700"
              >
                <p className="truncate text-xs font-medium text-neutral-200">{backlink.title}</p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-neutral-500">{backlink.excerpt}</p>
              </button>
            ))}
            {backlinks.length === 0 && <p className="text-sm text-neutral-500">No backlinks for this note.</p>}
          </div>
        </section>

        <section className="mt-4 rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-neutral-200">
            <Network size={15} />
            Graph view
          </div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs text-neutral-500">
            <div className="rounded border border-neutral-800 bg-neutral-950 p-2">
              <p className="text-lg font-semibold text-neutral-100">{graph.nodes.length}</p>
              Notes
            </div>
            <div className="rounded border border-neutral-800 bg-neutral-950 p-2">
              <p className="text-lg font-semibold text-neutral-100">{graph.edges.length}</p>
              Links
            </div>
          </div>
          <div className="mt-3 space-y-2">
            {connectedEdges.map((edge) => (
              <button
                key={`${edge.source}:${edge.target}`}
                type="button"
                onClick={() => setActivePath(edge.source === activePath ? edge.target : edge.source)}
                className="flex w-full items-center gap-2 rounded border border-neutral-800 bg-neutral-950 p-2 text-left font-mono text-[11px] text-neutral-400 hover:border-neutral-700"
              >
                <GitBranch size={13} />
                <span className="min-w-0 flex-1 truncate">{edge.source}</span>
                <span className="text-neutral-600">to</span>
                <span className="min-w-0 flex-1 truncate">{edge.target}</span>
              </button>
            ))}
            {connectedEdges.length === 0 && <p className="text-sm text-neutral-500">No graph links for this note.</p>}
          </div>
        </section>

        {error && <p className="mt-4 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</p>}
      </aside>
    </section>
  );
}
