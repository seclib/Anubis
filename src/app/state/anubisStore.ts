import { create } from "zustand";
import { ChatMessage } from "../core/api";
import { AnubisAgentV2 } from "../core/agent";
import { AnubisMemory } from "../core/memory";

export type AnubisView = "chat" | "vault" | "tools" | "plugins" | "settings";

const initialMessages: ChatMessage[] = [
  {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "ANUBIS MVP ready. Make sure Ollama is running qwen2.5-coder:7b, then send a message.",
    createdAt: new Date().toISOString(),
  },
];

let activeAbortController: AbortController | null = null;
const memory = new AnubisMemory();

type AnubisState = {
  activeView: AnubisView;
  currentStream: string;
  input: string;
  loading: boolean;
  messages: ChatMessage[];

  abortAgent: () => void;
  runAgent: (prompt?: string) => Promise<void>;
  setActiveView: (view: AnubisView) => void;
  setInput: (input: string) => void;
};

export const useAnubisStore = create<AnubisState>((set, get) => ({
  activeView: "chat",
  currentStream: "",
  input: "",
  loading: false,
  messages: initialMessages,

  abortAgent() {
    activeAbortController?.abort();
  },

  async runAgent(prompt) {
    const state = get();
    const nextPrompt = (prompt ?? state.input).trim();
    if (!nextPrompt || state.loading) {
      return;
    }

    const assistantId = crypto.randomUUID();
    set((current) => ({
      currentStream: "",
      input: "",
      loading: true,
      messages: [
        ...current.messages,
        createMessage("user", nextPrompt),
        {
          id: assistantId,
          role: "assistant",
          content: "",
          createdAt: new Date().toISOString(),
        },
      ],
    }));

    activeAbortController = new AbortController();
    const stream = createStreamBatcher(set, assistantId);

    try {
      const agent = new AnubisAgentV2({ memory });

      await agent.run(nextPrompt, {
        onText(text) {
          stream.schedule(text);
        },
        onToolCall(call) {
          set((current) => ({
            messages: [...current.messages, createMessage("system", `Tool requested: ${call.name}`)],
          }));
        },
        onToolResult(result) {
          set((current) => ({
            messages: [
              ...current.messages,
              createMessage(
                "system",
                `Tool ${result.status === "ok" ? "completed" : "blocked"}: ${result.tool}`,
              ),
            ],
          }));
        },
      }, activeAbortController.signal);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown runtime error";
      set((current) => ({
        currentStream: message,
        messages: updateMessage(current.messages, assistantId, `Runtime error: ${message}`),
      }));
    } finally {
      stream.flush();
      activeAbortController = null;
      set({ currentStream: "", loading: false });
    }
  },

  setActiveView(activeView) {
    set({ activeView });
  },

  setInput(input) {
    set({ input });
  },
}));

function createMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    createdAt: new Date().toISOString(),
  };
}

function updateMessage(messages: ChatMessage[], id: string, content: string): ChatMessage[] {
  return messages.map((message) => (message.id === id ? { ...message, content } : message));
}

type AnubisSetter = (updater: (state: AnubisState) => Partial<AnubisState>) => void;

function createStreamBatcher(set: AnubisSetter, assistantId: string) {
  let latestText = "";
  let scheduled = false;
  let frameId: number | null = null;

  function apply() {
    scheduled = false;
    frameId = null;
    set((current) => ({
      currentStream: latestText,
      messages: updateMessage(current.messages, assistantId, latestText),
    }));
  }

  return {
    schedule(text: string) {
      latestText = text;
      if (scheduled) {
        return;
      }

      scheduled = true;
      if (typeof window !== "undefined" && "requestAnimationFrame" in window) {
        frameId = window.requestAnimationFrame(apply);
      } else {
        globalThis.setTimeout(apply, 16);
      }
    },
    flush() {
      if (!scheduled) {
        return;
      }

      if (frameId !== null && typeof window !== "undefined") {
        window.cancelAnimationFrame(frameId);
      }
      apply();
    },
  };
}
