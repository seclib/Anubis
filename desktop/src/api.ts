const API_BASE = "http://127.0.0.1:8000";

export type WorkspaceNote = {
  id: string;
  title: string;
  path: string;
  content: string;
  updatedAt: string;
};

export type SearchResult = {
  id: string;
  title: string;
  path: string;
  excerpt: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

async function optionalRequest<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

function noteFromRemote(item: { path: string; title?: string; content?: string }): WorkspaceNote {
  return {
    id: item.path,
    title: item.title || item.path.split("/").pop()?.replace(/\.md$/, "") || "Untitled",
    path: item.path,
    content: item.content || "",
    updatedAt: new Date().toISOString()
  };
}

function encodeNotePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export async function loadNotes(): Promise<WorkspaceNote[] | null> {
  const notes = await optionalRequest<Array<{ path: string; title?: string }>>("/notes");
  if (!notes) return null;

  const hydrated = await Promise.all(
    notes.map(async (note) => {
      const payload = await optionalRequest<{ path: string; content: string }>(`/notes/${encodeNotePath(note.path)}`);
      return noteFromRemote({ ...note, content: payload?.content });
    })
  );
  return hydrated;
}

export async function saveNote(note: WorkspaceNote): Promise<boolean> {
  const payload = await optionalRequest<{ status?: string }>("/notes", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: note.path, content: note.content })
  });
  return payload?.status === "saved";
}

export async function searchWorkspace(query: string): Promise<SearchResult[] | null> {
  const payload = await optionalRequest<{ results?: Array<Omit<SearchResult, "id"> & { id?: string }> }>("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query })
  });
  return payload?.results?.map((result) => ({ ...result, id: result.id || result.path })) ?? null;
}

export async function sendChat(message: string, note: WorkspaceNote | null): Promise<string | null> {
  const payload = await optionalRequest<{ answer?: string }>("/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: note ? `${message}\n\nActive note: ${note.title}\n${note.content}` : message })
  });
  return payload?.answer ?? null;
}
