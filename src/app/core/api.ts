import { invoke } from "@tauri-apps/api/core";

export type Role = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
};

export type AgentReply = {
  answer: string;
  sources?: Array<{ path?: string; title?: string; excerpt?: string }>;
  raw?: unknown;
};

export type RuntimeHealth = {
  status: "online" | "offline";
  apiUrl: string;
  detail?: string;
};

export type PluginManifest = {
  name: string;
  displayName: string;
  description: string;
  enabled: boolean;
  entry?: string;
  permissions?: Array<"chat" | "commands" | "files" | "tools" | "ui">;
  triggers: string[];
  version?: string;
  source: string;
};

const apiUrl = import.meta.env.VITE_ANUBIS_API_URL ?? "http://127.0.0.1:8000";

function isTauriRuntime() {
  return "__TAURI_INTERNALS__" in window;
}

export async function sendAgentMessage(message: string): Promise<AgentReply> {
  if (isTauriRuntime()) {
    return invoke<AgentReply>("agent_chat", { message });
  }

  const response = await fetch(`${apiUrl}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: message, max_rounds: 2 }),
  });

  if (!response.ok) {
    throw new Error(`ANUBIS backend returned ${response.status}`);
  }

  const raw = await response.json();
  return normalizeAgentReply(raw);
}

export async function getRuntimeHealth(): Promise<RuntimeHealth> {
  if (isTauriRuntime()) {
    return invoke<RuntimeHealth>("runtime_health");
  }

  try {
    const response = await fetch(`${apiUrl}/health/live`);
    return {
      status: response.ok ? "online" : "offline",
      apiUrl,
      detail: response.ok ? undefined : `HTTP ${response.status}`,
    };
  } catch (error) {
    return {
      status: "offline",
      apiUrl,
      detail: error instanceof Error ? error.message : "Backend unavailable",
    };
  }
}

export async function listPlugins(): Promise<PluginManifest[]> {
  if (isTauriRuntime()) {
    return invoke<PluginManifest[]>("list_plugins");
  }

  return [];
}

export function normalizeAgentReply(raw: unknown): AgentReply {
  if (raw && typeof raw === "object") {
    const data = raw as Record<string, unknown>;
    const answer =
      stringValue(data.answer) ??
      stringValue(data.result) ??
      stringValue(data.response) ??
      stringValue(data.output) ??
      JSON.stringify(raw, null, 2);

    return {
      answer,
      sources: Array.isArray(data.sources) ? (data.sources as AgentReply["sources"]) : undefined,
      raw,
    };
  }

  return { answer: String(raw ?? ""), raw };
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}
