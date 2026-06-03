import { invoke } from "@tauri-apps/api/core";

export type MemoryRole = "system" | "user" | "assistant";

export type MemoryMessage = {
  id: string;
  role: MemoryRole;
  content: string;
  createdAt: string;
};

export type MemorySummary = {
  id: string;
  title: string;
  summary: string;
  keywords: string[];
  path: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};

export type MemoryContext = {
  shortTerm: MemoryMessage[];
  longTerm: MemorySummary[];
  text: string;
};

export type MemoryConfig = {
  memoryDir?: string;
  maxShortTermMessages?: number;
  maxShortTermChars?: number;
  summaryTriggerMessages?: number;
  summaryMaxChars?: number;
  retrievalLimit?: number;
};

type MemoryIndex = {
  version: 1;
  summaries: MemorySummary[];
};

type ToolResponse<T = unknown> = {
  tool: string;
  status: "ok" | "error";
  output: T;
  durationMs: number;
};

const DEFAULT_MEMORY_DIR = "vault/memory";
const DEFAULT_SHORT_TERM_MESSAGES = 20;
const DEFAULT_SHORT_TERM_CHARS = 12_000;
const DEFAULT_SUMMARY_TRIGGER_MESSAGES = 20;
const DEFAULT_SUMMARY_MAX_CHARS = 1_800;
const DEFAULT_RETRIEVAL_LIMIT = 4;
const INDEX_FILE = "index.json";

const STOP_WORDS = new Set([
  "about",
  "after",
  "again",
  "also",
  "and",
  "are",
  "because",
  "but",
  "can",
  "could",
  "from",
  "has",
  "have",
  "into",
  "not",
  "that",
  "the",
  "this",
  "was",
  "were",
  "what",
  "when",
  "with",
  "you",
  "your",
]);

export class AnubisMemory {
  private readonly memoryDir: string;
  private readonly indexPath: string;
  private readonly maxShortTermMessages: number;
  private readonly maxShortTermChars: number;
  private readonly summaryTriggerMessages: number;
  private readonly summaryMaxChars: number;
  private readonly retrievalLimit: number;
  private readonly shortTerm: MemoryMessage[] = [];
  private cachedIndex: MemoryIndex | null = null;

  constructor(config: MemoryConfig = {}) {
    this.memoryDir = trimSlashes(config.memoryDir ?? DEFAULT_MEMORY_DIR);
    this.indexPath = `${this.memoryDir}/${INDEX_FILE}`;
    this.maxShortTermMessages = config.maxShortTermMessages ?? DEFAULT_SHORT_TERM_MESSAGES;
    this.maxShortTermChars = config.maxShortTermChars ?? DEFAULT_SHORT_TERM_CHARS;
    this.summaryTriggerMessages = config.summaryTriggerMessages ?? DEFAULT_SUMMARY_TRIGGER_MESSAGES;
    this.summaryMaxChars = config.summaryMaxChars ?? DEFAULT_SUMMARY_MAX_CHARS;
    this.retrievalLimit = config.retrievalLimit ?? DEFAULT_RETRIEVAL_LIMIT;
  }

  async add(message: Pick<MemoryMessage, "role" | "content"> & Partial<MemoryMessage>): Promise<void> {
    const content = compactText(message.content, 4_000);
    if (!content) {
      return;
    }

    this.shortTerm.push({
      id: message.id ?? createId("msg"),
      role: message.role,
      content,
      createdAt: message.createdAt ?? new Date().toISOString(),
    });

    await this.compressIfNeeded();
  }

  async addPair(userContent: string, assistantContent: string): Promise<void> {
    await this.add({ role: "user", content: userContent });
    await this.add({ role: "assistant", content: assistantContent });
  }

  snapshotShortTerm(): MemoryMessage[] {
    return this.shortTerm.slice(-this.maxShortTermMessages);
  }

  clearShortTerm(): void {
    this.shortTerm.length = 0;
  }

  async retrieve(query: string, limit = this.retrievalLimit): Promise<MemoryContext> {
    const index = await this.readIndexSafe();
    const shortTerm = rankMessages(this.shortTerm, query).slice(0, Math.max(2, limit));
    const longTerm = rankSummaries(index.summaries, query).slice(0, limit);

    return {
      shortTerm,
      longTerm,
      text: formatMemoryContext(shortTerm, longTerm),
    };
  }

  async buildContext(query: string): Promise<MemoryContext> {
    return this.retrieve(query);
  }

  private async compressIfNeeded(): Promise<void> {
    const overMessageLimit = this.shortTerm.length > this.maxShortTermMessages;
    const overCharLimit = totalChars(this.shortTerm) > this.maxShortTermChars;

    if (!overMessageLimit && !overCharLimit) {
      return;
    }

    const overflowByCount = Math.max(0, this.shortTerm.length - this.maxShortTermMessages);
    const preferredChunkSize = Math.max(1, this.summaryTriggerMessages);
    const chunkSize = Math.min(
      this.shortTerm.length,
      Math.max(overflowByCount, overCharLimit ? Math.ceil(this.shortTerm.length / 3) : 1, preferredChunkSize),
    );
    const chunk = this.shortTerm.splice(0, chunkSize);

    if (chunk.length === 0) {
      return;
    }

    const summary = compressMessages(chunk, {
      memoryDir: this.memoryDir,
      maxChars: this.summaryMaxChars,
    });

    await this.persistSummary(summary);
  }

  private async persistSummary(summary: MemorySummary): Promise<void> {
    const index = await this.readIndexSafe();
    const nextIndex: MemoryIndex = {
      version: 1,
      summaries: [summary, ...index.summaries.filter((item) => item.id !== summary.id)].slice(0, 200),
    };

    await writeFile(summary.path, formatSummaryMarkdown(summary));
    await writeFile(this.indexPath, JSON.stringify(nextIndex, null, 2));
    this.cachedIndex = nextIndex;
  }

  private async readIndexSafe(): Promise<MemoryIndex> {
    if (this.cachedIndex) {
      return this.cachedIndex;
    }

    try {
      const raw = await readFile(this.indexPath);
      const parsed = JSON.parse(raw) as Partial<MemoryIndex>;
      this.cachedIndex = {
        version: 1,
        summaries: Array.isArray(parsed.summaries) ? parsed.summaries.filter(isMemorySummary) : [],
      };
      return this.cachedIndex;
    } catch {
      this.cachedIndex = { version: 1, summaries: [] };
      return this.cachedIndex;
    }
  }
}

export function compressMessages(
  messages: MemoryMessage[],
  options: { memoryDir?: string; maxChars?: number } = {},
): MemorySummary {
  const memoryDir = trimSlashes(options.memoryDir ?? DEFAULT_MEMORY_DIR);
  const maxChars = options.maxChars ?? DEFAULT_SUMMARY_MAX_CHARS;
  const createdAt = messages[0]?.createdAt ?? new Date().toISOString();
  const updatedAt = messages[messages.length - 1]?.createdAt ?? createdAt;
  const keywords = extractKeywords(messages.map((message) => message.content).join("\n"), 12);
  const title = buildTitle(messages, keywords);
  const summary = buildExtractiveSummary(messages, keywords, maxChars);
  const id = createId("memory");

  return {
    id,
    title,
    summary,
    keywords,
    path: `${memoryDir}/${id}-${slugify(title)}.md`,
    createdAt,
    updatedAt,
    messageCount: messages.length,
  };
}

export function formatMemoryContext(shortTerm: MemoryMessage[], longTerm: MemorySummary[]): string {
  const sections: string[] = [];

  if (longTerm.length > 0) {
    sections.push(
      [
        "Long-term memory:",
        ...longTerm.map((memory) => `- ${memory.title}: ${compactText(memory.summary, 420)}`),
      ].join("\n"),
    );
  }

  if (shortTerm.length > 0) {
    sections.push(
      [
        "Recent memory:",
        ...shortTerm.map((message) => `- ${message.role}: ${compactText(message.content, 320)}`),
      ].join("\n"),
    );
  }

  return compactText(sections.join("\n\n"), 3_500);
}

function buildExtractiveSummary(messages: MemoryMessage[], keywords: string[], maxChars: number): string {
  const keywordSet = new Set(keywords);
  const candidates = messages.flatMap((message) =>
    splitMemoryLines(message.content).map((line) => ({
      line: `${message.role}: ${line}`,
      score: scoreText(line, keywordSet) + (message.role === "user" ? 2 : 1),
    })),
  );

  const selected = candidates
    .filter((candidate) => candidate.line.length >= 16)
    .sort((left, right) => right.score - left.score)
    .slice(0, 8)
    .map((candidate) => candidate.line);

  const fallback = messages.map((message) => `${message.role}: ${compactText(message.content, 240)}`);
  return compactText((selected.length > 0 ? selected : fallback).join("\n"), maxChars);
}

function buildTitle(messages: MemoryMessage[], keywords: string[]): string {
  const firstUserMessage = messages.find((message) => message.role === "user" && message.content.trim());
  const source = firstUserMessage?.content ?? (keywords.join(" ") || "ANUBIS memory");
  return compactText(source.replace(/\s+/g, " "), 72);
}

function rankMessages(messages: MemoryMessage[], query: string): MemoryMessage[] {
  const queryTerms = new Set(tokenize(query));
  if (queryTerms.size === 0) {
    return messages.slice(-DEFAULT_SHORT_TERM_MESSAGES).reverse();
  }

  return [...messages]
    .map((message) => ({ message, score: scoreText(message.content, queryTerms) }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((entry) => entry.message);
}

function rankSummaries(summaries: MemorySummary[], query: string): MemorySummary[] {
  const queryTerms = new Set(tokenize(query));
  if (queryTerms.size === 0) {
    return summaries.slice().sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
  }

  return summaries
    .map((summary) => ({
      summary,
      score:
        scoreText(summary.title, queryTerms) * 2 +
        scoreText(summary.summary, queryTerms) +
        scoreText(summary.keywords.join(" "), queryTerms) * 3,
    }))
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .map((entry) => entry.summary);
}

function scoreText(text: string, queryTerms: Set<string>): number {
  const textTerms = new Set(tokenize(text));
  let score = 0;

  for (const term of queryTerms) {
    if (textTerms.has(term)) {
      score += 3;
    } else if (text.toLowerCase().includes(term)) {
      score += 1;
    }
  }

  return score;
}

function extractKeywords(text: string, limit: number): string[] {
  const counts = new Map<string, number>();
  for (const token of tokenize(text)) {
    counts.set(token, (counts.get(token) ?? 0) + 1);
  }

  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([token]) => token);
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/```[\s\S]*?```/g, " ")
    .match(/[a-z0-9_./-]{3,}/g)
    ?.filter((token) => !STOP_WORDS.has(token)) ?? [];
}

function splitMemoryLines(text: string): string[] {
  return text
    .replace(/```[\s\S]*?```/g, " [code block omitted] ")
    .split(/[\n.!?]+/)
    .map((line) => compactText(line, 360))
    .filter(Boolean);
}

async function readFile(path: string): Promise<string> {
  const response = await invokeTool<string>("read_file", { path });
  return String(response.output ?? "");
}

async function writeFile(path: string, content: string): Promise<void> {
  await invokeTool("write_file", { path, content });
}

async function invokeTool<T>(tool: string, payload: Record<string, unknown>): Promise<ToolResponse<T>> {
  if (!isTauriRuntime()) {
    throw new Error("Persistent memory is only available inside the Tauri runtime");
  }

  const response = await invoke<ToolResponse<T>>("route_tool", { tool, payload });
  if (response.status !== "ok") {
    throw new Error(String(response.output ?? `${tool} failed`));
  }

  return response;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function formatSummaryMarkdown(summary: MemorySummary): string {
  return [
    "---",
    `id: ${summary.id}`,
    `createdAt: ${summary.createdAt}`,
    `updatedAt: ${summary.updatedAt}`,
    `messageCount: ${summary.messageCount}`,
    `keywords: ${summary.keywords.join(", ")}`,
    "---",
    "",
    `# ${summary.title}`,
    "",
    summary.summary,
    "",
  ].join("\n");
}

function isMemorySummary(value: unknown): value is MemorySummary {
  if (!value || typeof value !== "object") {
    return false;
  }

  const summary = value as Partial<MemorySummary>;
  return (
    typeof summary.id === "string" &&
    typeof summary.title === "string" &&
    typeof summary.summary === "string" &&
    typeof summary.path === "string" &&
    Array.isArray(summary.keywords)
  );
}

function createId(prefix: string): string {
  const date = new Date()
    .toISOString()
    .split("-")
    .join("")
    .split(":")
    .join("")
    .split(".")
    .join("")
    .split("T")
    .join("")
    .split("Z")
    .join("")
    .slice(0, 14);
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `${prefix}-${date}-${random}`;
}

function slugify(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 56) || "summary"
  );
}

function compactText(value: string, maxChars: number): string {
  const compact = value.replace(/\s+/g, " ").trim();
  return compact.length > maxChars ? `${compact.slice(0, Math.max(0, maxChars - 1)).trim()}...` : compact;
}

function totalChars(messages: MemoryMessage[]): number {
  return messages.reduce((total, message) => total + message.content.length, 0);
}

function trimSlashes(value: string): string {
  return value.replace(/^\/+|\/+$/g, "");
}
