export type Role = "system" | "user" | "assistant" | "tool";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: string;
}

export interface RagSource {
  documentId: string;
  chunkId: string;
  title: string;
  score: number;
  excerpt: string;
}

export interface ToolExecutionLog {
  id: string;
  toolName: string;
  status: "pending" | "running" | "succeeded" | "failed";
  startedAt: string;
  finishedAt?: string;
  summary?: string;
}

export interface ChatRequest {
  conversationId?: string;
  message: string;
  workspaceId?: string;
}

export interface ChatResponse {
  conversationId: string;
  message: ChatMessage;
  sources: RagSource[];
  toolLogs: ToolExecutionLog[];
  requestId: string;
}
