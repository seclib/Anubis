export type AssistantMode = "short" | "deep" | "builder";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  starred?: boolean;
};

export type Project = {
  id: string;
  name: string;
  summary: string;
  memory: string;
  tags: string[];
  chats: Array<{ id: string; title: string; updatedAt: string; starred?: boolean }>;
  notes: Note[];
  files: Array<{ id: string; name: string; kind: string; size: string }>;
};

export type Note = {
  id: string;
  title: string;
  body: string;
  links: string[];
  updatedAt: string;
};

export type View = "chat" | "chats" | "projects" | "notes" | "files" | "settings";
