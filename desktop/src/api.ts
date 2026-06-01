const API_BASE = "http://127.0.0.1:8000";

export type NoteSummary = {
  path: string;
  title: string;
};

export type RagChunk = {
  id?: string;
  score?: number;
  path?: string;
  heading?: string;
  text?: string;
  line_start?: number;
  line_end?: number;
};

export async function listNotes(): Promise<Array<{ path: string; title: string }>> {
  const response = await fetch(`${API_BASE}/notes`);
  return response.json();
}

export async function readNote(path: string): Promise<{ path: string; content: string }> {
  const response = await fetch(`${API_BASE}/notes/${path}`);
  return response.json();
}

export async function writeNote(path: string, content: string): Promise<{ status: string; path: string }> {
  const response = await fetch(`${API_BASE}/notes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content })
  });
  return response.json();
}

export async function chat(
  message: string
): Promise<{ answer: string; chunks_used: RagChunk[]; memory_suggestion?: string | null }> {
  const response = await fetch(`${API_BASE}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  return response.json();
}
