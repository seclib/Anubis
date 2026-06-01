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

export async function loadNotes(): Promise<WorkspaceNote[] | null> {
  const payload = await optionalRequest<{ notes?: WorkspaceNote[] }>("/api/load-notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  return payload?.notes ?? null;
}

export async function saveNote(note: WorkspaceNote): Promise<boolean> {
  const payload = await optionalRequest<{ ok?: boolean }>("/api/save-note", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(note)
  });
  return Boolean(payload?.ok);
}

export async function searchWorkspace(query: string): Promise<SearchResult[] | null> {
  const payload = await optionalRequest<{ results?: SearchResult[] }>("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query })
  });
  return payload?.results ?? null;
}

export async function sendChat(message: string, note: WorkspaceNote | null): Promise<string | null> {
  const payload = await optionalRequest<{ answer?: string }>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, note })
  });
  return payload?.answer ?? null;
}
