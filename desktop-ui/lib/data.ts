import type { ChatMessage, Project } from "./types";

export const initialMessages: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "## Welcome to ANUBIS\n\nI can help you think through long-running work across projects, notes, and files.\n\n- Ask a focused question\n- Switch projects when context changes\n- Use builder mode for architecture and code plans",
  },
];

export const projects: Project[] = [
  {
    id: "desktop-ui",
    name: "ANUBIS Desktop UI",
    summary: "A premium, chat-first AI workspace with memory, projects, notes, and document intelligence.",
    memory:
      "The interface should feel like an Apple-grade operating system for AI cognition: calm, dark, layered, fluid, and never technical-looking.",
    tags: ["dev", "product", "research"],
    chats: [
      { id: "chat-1", title: "Interaction polish layer", updatedAt: "Just now", starred: true },
      { id: "chat-2", title: "Project memory isolation", updatedAt: "Today" },
    ],
    notes: [
      {
        id: "note-1",
        title: "Design Principles",
        body: "Dark mode, glass layers, chat-first navigation, invisible retrieval, and mobile-first desktop layout.",
        links: ["Motion Tokens", "Project Memory"],
        updatedAt: "Today",
      },
      {
        id: "note-2",
        title: "Motion Tokens",
        body: "Micro interactions use fast springs. Panels use slower spring motion. No linear animation.",
        links: ["Design Principles"],
        updatedAt: "Yesterday",
      },
    ],
    files: [
      { id: "file-1", name: "App shell architecture.md", kind: "Markdown", size: "18 KB" },
      { id: "file-2", name: "RAG memory notes.pdf", kind: "PDF", size: "2.1 MB" },
    ],
  },
  {
    id: "pentest-lab",
    name: "Pentest Research",
    summary: "Scoped workspace for authorized research notes, hypotheses, findings, and project memory.",
    memory: "Keep pentest research isolated from product UI work. Prefer summaries, scope boundaries, and evidence notes.",
    tags: ["pentest", "research"],
    chats: [{ id: "chat-3", title: "Research scope map", updatedAt: "Yesterday" }],
    notes: [
      {
        id: "note-3",
        title: "Scope Map",
        body: "Capture assets, rules of engagement, hypotheses, and open questions.",
        links: ["Findings"],
        updatedAt: "Yesterday",
      },
    ],
    files: [{ id: "file-3", name: "scope-map.md", kind: "Markdown", size: "9 KB" }],
  },
];
