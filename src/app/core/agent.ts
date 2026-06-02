import { invoke } from "@tauri-apps/api/core";

export type AgentRole = "system" | "user" | "assistant" | "tool";

export type AgentMessage = {
  role: AgentRole;
  content: string;
  createdAt?: string;
};

export type RagDocument = {
  id: string;
  text: string;
  title?: string;
  path?: string;
  keywords?: string[];
};

export type RagMatch = RagDocument & {
  score: number;
};

export type ToolCall = {
  name: string;
  payload: Record<string, unknown>;
};

export type ToolResult = {
  tool: string;
  output: unknown;
};

export type AgentRunResult = {
  answer: string;
  rag: RagMatch[];
  toolCalls: ToolCall[];
  toolResults: ToolResult[];
  aborted: boolean;
};

export type AgentCallbacks = {
  onToken?: (token: string) => void;
  onText?: (text: string) => void;
  onToolCall?: (call: ToolCall) => void;
  onToolResult?: (result: ToolResult) => void;
  onError?: (error: Error) => void;
  onDone?: (result: AgentRunResult) => void;
};

export type AgentConfig = {
  model?: string;
  ollamaUrl?: string;
  memory?: AgentMemory;
  ragDocuments?: RagDocument[];
  retrieveRag?: (query: string, signal?: AbortSignal) => RagMatch[] | Promise<RagMatch[]>;
  maxMessages?: number;
  maxMemoryChars?: number;
  maxPromptChars?: number;
  maxRagMatches?: number;
  requestOptions?: {
    numCtx?: number;
    temperature?: number;
    numPredict?: number;
  };
  summarize?: (messages: AgentMessage[]) => string | Promise<string>;
  executeTool?: (call: ToolCall, signal?: AbortSignal) => unknown | Promise<unknown>;
};

type OllamaChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
};

type OllamaStreamChunk = {
  message?: {
    content?: string;
  };
  response?: string;
  done?: boolean;
  error?: string;
};

const DEFAULT_MODEL = "qwen2.5-coder:7b";
const DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434";
const DEFAULT_MAX_MESSAGES = 8;
const DEFAULT_MAX_MEMORY_CHARS = 6000;
const DEFAULT_MAX_PROMPT_CHARS = 12000;
const DEFAULT_MAX_RAG_MATCHES = 4;
const TOOL_TAG_PATTERN = /<tool>([\s\S]*?)<\/tool>/gi;

export class AgentMemory {
  private messages: AgentMessage[];
  private summary = "";
  private readonly maxMessages: number;
  private readonly maxChars: number;
  private readonly summarize?: AgentConfig["summarize"];

  constructor(options: Pick<AgentConfig, "maxMessages" | "maxMemoryChars" | "summarize"> = {}) {
    this.messages = [];
    this.maxMessages = options.maxMessages ?? DEFAULT_MAX_MESSAGES;
    this.maxChars = options.maxMemoryChars ?? DEFAULT_MAX_MEMORY_CHARS;
    this.summarize = options.summarize;
  }

  snapshot(): AgentMessage[] {
    return [...this.messages];
  }

  getSummary(): string {
    return this.summary;
  }

  async add(message: AgentMessage): Promise<void> {
    this.messages.push({
      ...message,
      createdAt: message.createdAt ?? new Date().toISOString(),
    });
    await this.trim();
  }

  async addPair(user: string, assistant: string): Promise<void> {
    await this.add({ role: "user", content: user });
    await this.add({ role: "assistant", content: assistant });
  }

  clear(): void {
    this.messages = [];
    this.summary = "";
  }

  private async trim(): Promise<void> {
    while (this.messages.length > this.maxMessages || totalChars(this.messages) > this.maxChars) {
      const removed = this.messages.splice(0, Math.max(1, this.messages.length - this.maxMessages));
      if (!removed.length) {
        break;
      }

      if (this.summarize) {
        const nextSummary = await this.summarize(removed);
        if (nextSummary.trim()) {
          this.summary = compactText([this.summary, nextSummary].filter(Boolean).join("\n"), this.maxChars / 2);
        }
      } else if (!this.summary) {
        this.summary = compactText(removed.map((item) => `${item.role}: ${item.content}`).join("\n"), 1200);
      }
    }
  }
}

export class AnubisAgentV2 {
  private readonly model: string;
  private readonly ollamaUrl: string;
  private readonly memory: AgentMemory;
  private readonly ragDocuments: RagDocument[];
  private readonly retrieveRag?: NonNullable<AgentConfig["retrieveRag"]>;
  private readonly maxPromptChars: number;
  private readonly maxRagMatches: number;
  private readonly requestOptions: Required<NonNullable<AgentConfig["requestOptions"]>>;
  private readonly executeTool?: AgentConfig["executeTool"];

  constructor(config: AgentConfig = {}) {
    this.model = config.model ?? envValue("VITE_OLLAMA_MODEL", DEFAULT_MODEL);
    this.ollamaUrl = trimTrailingSlash(config.ollamaUrl ?? envValue("VITE_OLLAMA_URL", DEFAULT_OLLAMA_URL));
    this.memory =
      config.memory ??
      new AgentMemory({
        maxMessages: config.maxMessages,
        maxMemoryChars: config.maxMemoryChars,
        summarize: config.summarize,
      });
    this.ragDocuments = config.ragDocuments ?? [];
    this.retrieveRag = config.retrieveRag;
    this.maxPromptChars = config.maxPromptChars ?? DEFAULT_MAX_PROMPT_CHARS;
    this.maxRagMatches = config.maxRagMatches ?? DEFAULT_MAX_RAG_MATCHES;
    this.requestOptions = {
      numCtx: config.requestOptions?.numCtx ?? 4096,
      temperature: config.requestOptions?.temperature ?? 0.2,
      numPredict: config.requestOptions?.numPredict ?? 1024,
    };
    this.executeTool = config.executeTool;
  }

  async run(input: string, callbacks: AgentCallbacks = {}, signal?: AbortSignal): Promise<AgentRunResult> {
    const prompt = input.trim();
    if (!prompt) {
      return { answer: "", rag: [], toolCalls: [], toolResults: [], aborted: false };
    }

    const rag = await this.collectRag(prompt, signal);
    const messages = buildPrompt({
      input: prompt,
      memory: this.memory.snapshot(),
      memorySummary: this.memory.getSummary(),
      rag,
      maxChars: this.maxPromptChars,
    });

    let answer = "";
    let aborted = false;

    try {
      for await (const token of streamOllamaChat(
        {
          model: this.model,
          ollamaUrl: this.ollamaUrl,
          messages,
          options: this.requestOptions,
        },
        signal,
      )) {
        answer += token;
        callbacks.onToken?.(token);
        callbacks.onText?.(answer);
      }
    } catch (error) {
      if (isAbortError(error) || signal?.aborted) {
        aborted = true;
      } else {
        const normalized = normalizeError(error);
        callbacks.onError?.(normalized);
        throw normalized;
      }
    }

    const toolCalls = detectToolCalls(answer);
    const toolResults: ToolResult[] = [];

    if (!aborted) {
      for (const toolCall of toolCalls) {
        callbacks.onToolCall?.(toolCall);
        const output = await this.runTool(toolCall, signal);
        const result = { tool: toolCall.name, output };
        toolResults.push(result);
        callbacks.onToolResult?.(result);
      }

      await this.memory.addPair(prompt, stripToolMarkup(answer));
    }

    const result = { answer, rag, toolCalls, toolResults, aborted };
    callbacks.onDone?.(result);
    return result;
  }

  private async runTool(call: ToolCall, signal?: AbortSignal): Promise<unknown> {
    if (this.executeTool) {
      return this.executeTool(call, signal);
    }

    if (!isTauriRuntime()) {
      throw new Error(`Tool execution requires Tauri runtime: ${call.name}`);
    }

    return invoke("route_tool", {
      tool: call.name,
      payload: call.payload,
    });
  }

  private async collectRag(query: string, signal?: AbortSignal): Promise<RagMatch[]> {
    const localMatches = lightRagSearch(query, this.ragDocuments, this.maxRagMatches);
    const externalMatches = this.retrieveRag ? await this.retrieveRag(query, signal) : [];
    return dedupeRagMatches([...externalMatches, ...localMatches]).slice(0, this.maxRagMatches);
  }
}

export function buildPrompt(args: {
  input: string;
  memory: AgentMessage[];
  memorySummary?: string;
  rag?: RagMatch[];
  maxChars?: number;
}): OllamaChatMessage[] {
  const maxChars = args.maxChars ?? DEFAULT_MAX_PROMPT_CHARS;
  const system = compactText(
    [
      "You are ANUBIS, a local AI coding agent running on Qwen2.5-Coder 7B.",
      "Optimize for concise, correct engineering help with minimal context usage.",
      "Use provided memory and RAG snippets only when relevant.",
      "When a tool is required, output exactly one tool call and no prose.",
      'JSON tool format: {"tool":"name","payload":{}}',
      'Tag tool format: <tool>{"name":"name","payload":{}}</tool>',
      "If no tool is required, answer normally.",
    ].join("\n"),
    1400,
  );

  const memoryBlock = [
    args.memorySummary ? `Summary:\n${args.memorySummary}` : "",
    args.memory.map((item) => `${item.role}: ${item.content}`).join("\n"),
  ]
    .filter(Boolean)
    .join("\n\n");

  const ragBlock = (args.rag ?? [])
    .map((item, index) => {
      const label = item.title || item.path || item.id;
      return `[${index + 1}] ${label}\n${compactText(item.text, 900)}`;
    })
    .join("\n\n");

  const context = compactText(
    [
      memoryBlock ? `Recent memory:\n${memoryBlock}` : "",
      ragBlock ? `Relevant local context:\n${ragBlock}` : "",
    ]
      .filter(Boolean)
      .join("\n\n"),
    Math.max(1000, maxChars - system.length - args.input.length - 600),
  );

  return [
    { role: "system", content: system },
    ...(context ? [{ role: "system" as const, content: context }] : []),
    { role: "user", content: compactText(args.input, Math.max(1000, maxChars / 3)) },
  ];
}

export function lightRagSearch(query: string, docs: RagDocument[], limit = DEFAULT_MAX_RAG_MATCHES): RagMatch[] {
  const queryTerms = tokenize(query);
  if (!queryTerms.length || !docs.length) {
    return [];
  }

  return docs
    .map((doc) => {
      const haystack = tokenize([doc.title, doc.path, doc.keywords?.join(" "), doc.text].filter(Boolean).join(" "));
      const uniqueHaystack = new Set(haystack);
      const score = queryTerms.reduce((sum, term) => sum + (uniqueHaystack.has(term) ? 1 : 0), 0);
      return { ...doc, score };
    })
    .filter((doc) => doc.score > 0)
    .sort((left, right) => right.score - left.score || left.text.length - right.text.length)
    .slice(0, limit);
}

export function detectToolCalls(text: string): ToolCall[] {
  const calls: ToolCall[] = [];
  let match: RegExpExecArray | null;

  while ((match = TOOL_TAG_PATTERN.exec(text)) !== null) {
    const parsed = parseToolJson(match[1]);
    if (parsed) {
      calls.push(parsed);
    }
  }

  const trimmed = text.trim();
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    const parsed = parseToolJson(trimmed);
    if (parsed) {
      calls.push(parsed);
    }
  }

  return dedupeToolCalls(calls);
}

export async function* streamOllamaChat(
  args: {
    model: string;
    ollamaUrl: string;
    messages: OllamaChatMessage[];
    options: Required<NonNullable<AgentConfig["requestOptions"]>>;
  },
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const response = await fetch(`${trimTrailingSlash(args.ollamaUrl)}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: args.model,
      messages: args.messages,
      stream: true,
      keep_alive: "30m",
      options: {
        num_ctx: args.options.numCtx,
        temperature: args.options.temperature,
        num_predict: args.options.numPredict,
      },
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Ollama returned HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const token = parseOllamaToken(line);
        if (token) {
          yield token;
        }
      }
    }

    const token = parseOllamaToken(buffer);
    if (token) {
      yield token;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseOllamaToken(line: string): string {
  const trimmed = line.trim();
  if (!trimmed) {
    return "";
  }

  const data = JSON.parse(trimmed) as OllamaStreamChunk;
  if (data.error) {
    throw new Error(data.error);
  }

  return data.message?.content ?? data.response ?? "";
}

function parseToolJson(raw: string): ToolCall | null {
  try {
    const parsed = JSON.parse(raw.trim()) as Record<string, unknown>;
    const name = stringValue(parsed.tool) ?? stringValue(parsed.name);
    const payload = isRecord(parsed.payload) ? parsed.payload : {};
    return name ? { name, payload } : null;
  } catch {
    return null;
  }
}

function dedupeToolCalls(calls: ToolCall[]): ToolCall[] {
  const seen = new Set<string>();
  return calls.filter((call) => {
    const key = `${call.name}:${JSON.stringify(call.payload)}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function dedupeRagMatches(matches: RagMatch[]): RagMatch[] {
  const seen = new Set<string>();
  return matches.filter((match) => {
    const key = match.path || match.id || match.text.slice(0, 80);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function stripToolMarkup(text: string): string {
  return text.replace(TOOL_TAG_PATTERN, "").trim();
}

function tokenize(value: string): string[] {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_./-]+/g, " ")
    .split(/\s+/)
    .filter((term) => term.length > 2);
}

function compactText(value: string, maxChars: number): string {
  const normalized = value.replace(/\s+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  if (normalized.length <= maxChars) {
    return normalized;
  }

  return `${normalized.slice(0, Math.max(0, maxChars - 16)).trimEnd()}\n...[trimmed]`;
}

function totalChars(messages: AgentMessage[]): number {
  return messages.reduce((sum, message) => sum + message.content.length, 0);
}

function envValue(name: string, fallback: string): string {
  return String(import.meta.env[name] ?? fallback);
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
