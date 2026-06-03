export type VaultNote = {
  path: string;
  title: string;
  preview: string;
  tags: string[];
  links: string[];
  updated_at: number;
  size_bytes: number;
};

export type VaultBacklink = {
  source_path: string;
  title: string;
  excerpt: string;
  line: number;
};

export type VaultGraphNode = {
  id: string;
  path: string;
  title: string;
  tags: string[];
};

export type VaultGraphEdge = {
  source: string;
  target: string;
  type: string;
};

export type VaultGraph = {
  nodes: VaultGraphNode[];
  edges: VaultGraphEdge[];
};

export type VaultSearchResult = {
  path: string;
  title: string;
  score: number;
  excerpt: string;
  source: "local" | "memory";
};

export type VaultSnapshot = {
  notes: VaultNote[];
  graph: VaultGraph;
};

export async function vaultSnapshot(): Promise<VaultSnapshot> {
  return getVault<VaultSnapshot>("/snapshot");
}

export async function readVaultNote(path: string): Promise<{ path: string; content: string }> {
  return getVault<{ path: string; content: string }>(`/notes/${encodeURIComponentPath(path)}`);
}

export async function writeVaultNote(path: string, content: string, index = true) {
  const response = await fetch("/api/vault/notes", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content, index }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function vaultBacklinks(path: string): Promise<VaultBacklink[]> {
  const payload = await getVault<{ backlinks: VaultBacklink[] }>(`/backlinks?path=${encodeURIComponent(path)}`);
  return payload.backlinks;
}

export async function searchVault(query: string, limit = 8): Promise<VaultSearchResult[]> {
  const trimmed = query.trim();
  if (!trimmed) {
    return [];
  }
  const payload = await getVault<{ results: VaultSearchResult[] }>(
    `/search?query=${encodeURIComponent(trimmed)}&limit=${limit}`,
  );
  return payload.results;
}

async function getVault<T>(path: string): Promise<T> {
  const response = await fetch(`/api/vault${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as T;
}

function encodeURIComponentPath(path: string): string {
  return path
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}
