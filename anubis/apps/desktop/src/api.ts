import { invoke } from "@tauri-apps/api/core";

export interface ChatMessage {
  id: string;
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  created_at: string;
}

export interface RagSource {
  document_id: string;
  chunk_id: string;
  title: string;
  score: number;
  excerpt: string;
}

export interface ToolExecutionLog {
  id: string;
  tool_name: string;
  status: "pending" | "running" | "succeeded" | "failed";
  started_at: string;
  finished_at?: string;
  summary?: string;
}

export interface ChatResponse {
  conversation_id: string;
  message: ChatMessage;
  sources: RagSource[];
  tool_logs: ToolExecutionLog[];
  request_id: string;
}

export async function sendChatMessage(message: string, conversationId?: string): Promise<ChatResponse> {
  return invoke<ChatResponse>("send_chat_message", {
    request: {
      message,
      conversation_id: conversationId
    }
  });
}
