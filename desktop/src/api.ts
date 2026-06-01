const API_BASE = "http://127.0.0.1:8000";
const WS_BASE = "ws://127.0.0.1:8000";

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

export type SkillNode = {
  id: string;
  label?: string;
  type: string;
  path?: string;
  status?: string;
  objective?: string;
  dependencies?: string[];
  triggers?: string[];
  mutation_rules?: string[];
  fitness?: Record<string, number>;
  markdown?: string;
};

export type SkillEdge = {
  id: string;
  source: string;
  target: string;
  type: "depends_on" | "enhances" | "merges_into" | "conflicts_with" | "derived_from" | string;
  weight?: number;
  evidence?: string;
};

export type SkillCluster = {
  id: string;
  label: string;
  members: string[];
  size: number;
  average_fitness?: number;
};

export type SkillGraph = {
  nodes: SkillNode[];
  edges: SkillEdge[];
  clusters: SkillCluster[];
  evolution_paths?: Array<{ root: string; path: string[]; length: number }>;
  insights: {
    most_used_skills?: Array<{ id: string; usage_frequency: number; overall: number }>;
    isolated_skills?: string[];
    critical_clusters?: SkillCluster[];
    weak_dependencies?: string[];
    central_skills?: Array<{ id: string; degree: number; incoming: number }>;
    newly_created_skills?: string[];
  };
  changes?: {
    added_nodes: string[];
    removed_nodes: string[];
    added_edges: string[];
    removed_edges: string[];
    changed_nodes: string[];
  };
};

export type BrainStatus = {
  status: string;
  detail: string;
};

export type BrainLogEntry = {
  timestamp?: number;
  component: string;
  level?: string;
  message: string;
};

export type BrainAgent = {
  name: string;
  role: string;
  model: string;
  status: string;
  current_task: string;
};

export type BrainExecution = {
  agent: string;
  task: string;
  status: string;
  started_at?: number;
  duration_ms?: number;
};

export type BrainSnapshot = {
  timestamp: number;
  system_health: Record<"backend" | "qdrant" | "agent" | "launcher", BrainStatus>;
  memory: {
    vault: {
      path: string;
      size_bytes: number;
      updated_at?: number | null;
    };
    notes: number;
    skills: number;
    chunks: number;
    embeddings: number;
    qdrant: BrainStatus & {
      url: string;
      collection: string;
      embedding_count: number;
    };
  };
  agent_activity: {
    active_agents: BrainAgent[];
    current_tasks: Array<{ agent: string; task: string; status: string }>;
    last_executions: BrainExecution[];
  };
  logs: BrainLogEntry[];
  architecture: {
    frontend: string;
    backend: string;
    live_updates: string;
    modules: Array<{ id: string; label: string; depends_on: string[] }>;
  };
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

export async function listSkills(): Promise<SkillNode[]> {
  const response = await fetch(`${API_BASE}/api/skills`);
  return response.json();
}

export async function readSkillGraph(): Promise<SkillGraph> {
  const response = await fetch(`${API_BASE}/api/skill-graph`);
  return response.json();
}

export function openSkillUpdates(
  onGraph: (graph: SkillGraph) => void,
  onError: () => void
): () => void {
  const events = new EventSource(`${API_BASE}/api/skill-updates`);
  events.addEventListener("skill-graph", (event) => {
    onGraph(JSON.parse((event as MessageEvent).data));
  });
  events.onerror = () => onError();
  return () => events.close();
}

export async function readBrainSnapshot(): Promise<BrainSnapshot> {
  const response = await fetch(`${API_BASE}/brain/snapshot`);
  return response.json();
}

export function openBrainUpdates(
  onSnapshot: (snapshot: BrainSnapshot, logs: BrainLogEntry[]) => void,
  onError: () => void
): () => void {
  const socket = new WebSocket(`${WS_BASE}/brain/ws`);
  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "brain.snapshot") {
      onSnapshot(payload.snapshot, payload.logs || []);
    }
  };
  socket.onerror = () => onError();
  return () => socket.close();
}
