import { create } from "zustand";
import {
  ChatMessage,
  PluginManifest,
  RuntimeHealth,
  getRuntimeHealth,
  listPlugins,
} from "../core/api";
import { AgentMemory, AnubisAgentV2, RagDocument } from "../core/agent";
import { createVaultRagRetriever } from "../core/rag";
import type { ModuleRuntimeState } from "../core/modules/moduleTypes";

const initialMessages: ChatMessage[] = [
  {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "ANUBIS runtime ready. Ask me to reason over the local vault, inspect a project, or route work through a plugin.",
    createdAt: new Date().toISOString(),
  },
];

const initialModuleRuntime: ModuleRuntimeState = {
  chatActions: [],
  commands: [],
  loaded: [],
  tools: [],
};

const agentMemory = new AgentMemory({
  maxMessages: 8,
  maxMemoryChars: 6000,
  summarize: (messages) =>
    messages
      .map((message) => `${message.role}: ${message.content}`)
      .join("\n")
      .slice(0, 1200),
});

type AnubisState = {
  busy: boolean;
  health: RuntimeHealth;
  input: string;
  messages: ChatMessage[];
  moduleRuntime: ModuleRuntimeState;
  paletteOpen: boolean;
  pluginOverrides: Record<string, boolean>;
  plugins: PluginManifest[];

  appendSystemNote: (content: string) => void;
  closePalette: () => void;
  openPalette: () => void;
  refreshRuntime: () => Promise<void>;
  runAgent: (prompt?: string) => Promise<void>;
  setInput: (input: string) => void;
  setModuleRuntime: (runtime: ModuleRuntimeState) => void;
  togglePalette: () => void;
  togglePlugin: (pluginName: string) => void;
};

export const useAnubisStore = create<AnubisState>((set, get) => ({
  busy: false,
  health: { status: "offline", apiUrl: "http://127.0.0.1:8000" },
  input: "",
  messages: initialMessages,
  moduleRuntime: initialModuleRuntime,
  paletteOpen: false,
  pluginOverrides: {},
  plugins: [],

  appendSystemNote(content) {
    set((state) => ({
      messages: [...state.messages, createMessage("system", content)],
    }));
  },

  closePalette() {
    set({ paletteOpen: false });
  },

  openPalette() {
    set({ paletteOpen: true });
  },

  async refreshRuntime() {
    const [health, plugins] = await Promise.all([getRuntimeHealth(), listPlugins().catch(() => [])]);
    set({ health, plugins });
  },

  async runAgent(prompt) {
    const state = get();
    const nextPrompt = (prompt ?? state.input).trim();
    if (!nextPrompt || state.busy) {
      return;
    }

    const assistantId = crypto.randomUUID();
    set((current) => ({
      busy: true,
      input: "",
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

    try {
      const agent = new AnubisAgentV2({
        memory: agentMemory,
        ragDocuments: buildRagDocuments(get()),
        retrieveRag: createVaultRagRetriever({
          vaultPath: "vault",
          maxBytes: 4096,
          maxMatches: 4,
        }),
      });

      await agent.run(nextPrompt, {
        onText(text) {
          set((current) => ({
            messages: updateMessage(current.messages, assistantId, text),
          }));
        },
        onToolCall(call) {
          set((current) => ({
            messages: [
              ...current.messages,
              createMessage("system", `Tool requested: ${call.name}`),
            ],
          }));
        },
        onToolResult(result) {
          set((current) => ({
            messages: [
              ...current.messages,
              createMessage("system", `Tool completed: ${result.tool}`),
            ],
          }));
        },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown runtime error";
      set((current) => ({
        messages: updateMessage(current.messages, assistantId, `Runtime error: ${message}`),
      }));
    } finally {
      set({ busy: false });
    }
  },

  setInput(input) {
    set({ input });
  },

  setModuleRuntime(runtime) {
    set({ moduleRuntime: runtime });
  },

  togglePalette() {
    set((state) => ({ paletteOpen: !state.paletteOpen }));
  },

  togglePlugin(pluginName) {
    const state = get();
    const plugin = state.plugins.find((item) => item.name === pluginName);
    const nextEnabled = !(state.pluginOverrides[pluginName] ?? plugin?.enabled ?? true);

    set((current) => ({
      pluginOverrides: { ...current.pluginOverrides, [pluginName]: nextEnabled },
      messages: [
        ...current.messages,
        createMessage("system", `${plugin?.displayName ?? pluginName} ${nextEnabled ? "enabled" : "disabled"}.`),
      ],
    }));
  },
}));

export function selectEffectivePlugins(state: Pick<AnubisState, "plugins" | "pluginOverrides">) {
  return state.plugins.map((plugin) => ({
    ...plugin,
    enabled: state.pluginOverrides[plugin.name] ?? plugin.enabled,
  }));
}

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

function buildRagDocuments(state: AnubisState): RagDocument[] {
  const effectivePlugins = selectEffectivePlugins(state).filter((plugin) => plugin.enabled);
  const pluginDocs = effectivePlugins.map((plugin) => ({
    id: `plugin:${plugin.name}`,
    title: plugin.displayName,
    path: plugin.source,
    keywords: [plugin.name, plugin.displayName, ...plugin.triggers],
    text: [
      plugin.displayName,
      plugin.description,
      plugin.triggers.join(" "),
      plugin.permissions?.join(" ") ?? "",
    ]
      .filter(Boolean)
      .join("\n"),
  }));

  const commandDocs = state.moduleRuntime.commands.map((command) => ({
    id: `command:${command.id}`,
    title: command.label,
    keywords: [command.id, command.group, ...(command.keywords ?? [])],
    text: [command.label, command.description, command.group, ...(command.keywords ?? [])].join("\n"),
  }));

  return [...pluginDocs, ...commandDocs];
}
