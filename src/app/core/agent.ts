import type { AnubisMemory } from "./memory";
import { formatRagContext, retrieveLightRag } from "./rag";
import { detectToolCalls, executeToolCall, stripToolMarkup } from "./tools";
import type { ToolCall, ToolResult } from "./tools";

export type AgentRole = "system" | "user" | "assistant";

export type AgentMessage = {
  role: AgentRole;
  content: string;
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

export type { ToolCall, ToolResult } from "./tools";

export type AgentRunResult = {
  answer: string;
  rag: RagMatch[];
  toolCalls: ToolCall[];
  toolResults: ToolResult[];
  aborted: boolean;
};

export type AgentPipelineStage =
  | "context"
  | "prompt"
  | "stream"
  | "tool_detection"
  | "tool_execution"
  | "memory_write"
  | "done";

export type AgentCallbacks = {
  onToken?: (token: string) => void;
  onText?: (text: string) => void;
  onStage?: (stage: AgentPipelineStage) => void;
  onToolCall?: (call: ToolCall) => void;
  onToolResult?: (result: ToolResult) => void;
  onError?: (error: Error) => void;
  onDone?: (result: AgentRunResult) => void;
};

export type AgentConfig = {
  model?: string;
  ollamaUrl?: string;
  memory?: AnubisMemory;
  rag?: false | {
    retrieve?: (query: string, signal?: AbortSignal) => RagMatch[] | Promise<RagMatch[]>;
    maxContextChars?: number;
  };
  maxPromptChars?: number;
  requestOptions?: {
    numCtx?: number;
    temperature?: number;
    numPredict?: number;
  };
};

type OllamaChatMessage = {
  role: "system" | "user" | "assistant";
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
const DEFAULT_OLLAMA_URL = "http://localhost:11434";
const DEFAULT_MAX_PROMPT_CHARS = 7_000;

type PipelineContext = {
  memoryContext?: string;
  ragContext?: string;
  ragMatches: RagMatch[];
};

// Compatibility shim for the MVP store. The MVP agent does not read or retain memory.
export class AgentMemory {
  constructor(_options: unknown = {}) {}
  snapshot(): AgentMessage[] {
    return [];
  }
  getSummary(): string {
    return "";
  }
  async add(): Promise<void> {}
  async addPair(): Promise<void> {}
  clear(): void {}
}

export class AnubisAgentV2 {
  private readonly model: string;
  private readonly ollamaUrl: string;
  private readonly memory?: AnubisMemory;
  private readonly rag: NonNullable<AgentConfig["rag"]> | false;
  private readonly maxPromptChars: number;
  private readonly requestOptions: Required<NonNullable<AgentConfig["requestOptions"]>>;

  constructor(config: AgentConfig = {}) {
    this.model = config.model ?? envValue("VITE_OLLAMA_MODEL", DEFAULT_MODEL);
    this.ollamaUrl = trimTrailingSlash(config.ollamaUrl ?? envValue("VITE_OLLAMA_URL", DEFAULT_OLLAMA_URL));
    this.memory = config.memory;
    this.rag = config.rag ?? {};
    this.maxPromptChars = config.maxPromptChars ?? DEFAULT_MAX_PROMPT_CHARS;
    this.requestOptions = {
      numCtx: config.requestOptions?.numCtx ?? 4096,
      temperature: config.requestOptions?.temperature ?? 0.2,
      numPredict: config.requestOptions?.numPredict ?? 1024,
    };
  }

  async run(input: string, callbacks: AgentCallbacks = {}, signal?: AbortSignal): Promise<AgentRunResult> {
    const prompt = input.trim();
    if (!prompt) {
      return emptyResult(false);
    }

    let aborted = false;
    callbacks.onStage?.("context");
    const context = await this.buildPipelineContext(prompt, signal);
    callbacks.onStage?.("prompt");
    const messages = buildPrompt(prompt, {
      memoryContext: context.memoryContext,
      ragContext: context.ragContext,
      maxChars: this.maxPromptChars,
    });

    let answer = "";

    try {
      callbacks.onStage?.("stream");
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

    callbacks.onStage?.("tool_detection");
    const toolCalls = aborted ? [] : detectToolCalls(answer);
    callbacks.onStage?.("tool_execution");
    const toolResults = await this.executeTools(toolCalls, callbacks);

    const cleanedAnswer = stripToolMarkup(answer) || answer;
    const result: AgentRunResult = {
      answer,
      rag: context.ragMatches,
      toolCalls,
      toolResults,
      aborted,
    };
    if (!aborted && cleanedAnswer.trim()) {
      callbacks.onStage?.("memory_write");
      await this.memory?.addPair(prompt, cleanedAnswer).catch(() => undefined);
    }
    callbacks.onStage?.("done");
    callbacks.onDone?.(result);
    return result;
  }

  private async buildPipelineContext(input: string, signal?: AbortSignal): Promise<PipelineContext> {
    const [memoryContext, ragMatches] = await Promise.all([
      this.memory?.buildContext(input).catch(() => undefined),
      this.collectRag(input, signal),
    ]);

    return {
      memoryContext: memoryContext?.text,
      ragContext: formatRagContext(ragMatches, this.rag ? this.rag.maxContextChars : undefined),
      ragMatches,
    };
  }

  private async executeTools(toolCalls: ToolCall[], callbacks: AgentCallbacks): Promise<ToolResult[]> {
    const results: ToolResult[] = [];

    for (const toolCall of toolCalls) {
      callbacks.onToolCall?.(toolCall);
      const toolResult = await executeToolCall(toolCall);
      results.push(toolResult);
      callbacks.onToolResult?.(toolResult);
    }

    return results;
  }

  private async collectRag(query: string, signal?: AbortSignal): Promise<RagMatch[]> {
    if (this.rag === false) {
      return [];
    }

    if (this.rag.retrieve) {
      return Promise.resolve(this.rag.retrieve(query, signal)).catch(() => []);
    }

    return retrieveLightRag(query, { maxContextChars: this.rag.maxContextChars }, signal).catch(() => []);
  }
}

export function buildPrompt(
  prompt: string,
  context: {
    memoryContext?: string;
    ragContext?: string;
    maxChars?: number;
  } = {},
): OllamaChatMessage[] {
  const maxChars = context.maxChars ?? DEFAULT_MAX_PROMPT_CHARS;
  const contextText = compactText(
    [context.memoryContext, context.ragContext].filter(Boolean).join("\n\n"),
    Math.max(0, maxChars - prompt.length - 1_200),
  );
  const userContent = contextText
    ? `Relevant context:\n${contextText}\n\nCurrent user request:\n${compactText(prompt, Math.max(1_000, maxChars / 3))}`
    : compactText(prompt, maxChars);

  return [
    {
      role: "system",
      content:
        'You are ANUBIS, a local AI coding assistant. Use provided memory and local context only when relevant. Answer clearly and concisely. Do not claim to edit files or run commands. If a safe tool is required, output exactly one JSON tool call like {"tool":"read_file","payload":{"path":"vault/README.md"}} or <tool>{"name":"git_status","payload":{}}</tool>.',
    },
    {
      role: "user",
      content: userContent,
    },
  ];
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
      options: {
        num_ctx: args.options.numCtx,
        temperature: args.options.temperature,
        num_predict: args.options.numPredict,
      },
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Ollama returned HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Ollama response did not include a stream body");
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

  const chunk = JSON.parse(trimmed) as OllamaStreamChunk;
  if (chunk.error) {
    throw new Error(chunk.error);
  }

  return chunk.message?.content ?? chunk.response ?? "";
}

function emptyResult(aborted: boolean): AgentRunResult {
  return {
    answer: "",
    rag: [],
    toolCalls: [],
    toolResults: [],
    aborted,
  };
}

function envValue(name: string, fallback: string): string {
  return String(import.meta.env[name] ?? fallback);
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function compactText(value: string, maxChars: number): string {
  if (maxChars <= 0) {
    return "";
  }

  const normalized = value.replace(/\n{3,}/g, "\n\n").trim();
  if (normalized.length <= maxChars) {
    return normalized;
  }

  return `${normalized.slice(0, Math.max(0, maxChars - 14)).trimEnd()}\n...[trimmed]`;
}

function normalizeError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
