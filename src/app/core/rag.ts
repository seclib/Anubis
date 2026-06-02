import { invoke } from "@tauri-apps/api/core";
import type { RagMatch } from "./agent";

export type VaultRagOptions = {
  vaultPath?: string;
  maxBytes?: number;
  maxMatches?: number;
  cacheTtlMs?: number;
};

type SearchFilesResult = {
  matches?: Array<{
    path?: string;
    line?: number;
    text?: string;
  }>;
};

type ReadFileResult = {
  path?: string;
  content?: string;
};

type ToolResponse<T> = {
  output?: T;
  status?: string;
  tool?: string;
};

type CachedQuery = {
  expiresAt: number;
  matches: RagMatch[];
};

const DEFAULT_VAULT_PATH = "vault";
const DEFAULT_MAX_BYTES = 4096;
const DEFAULT_MAX_MATCHES = 6;
const DEFAULT_CACHE_TTL_MS = 15_000;
const QUERY_PREFIX_LENGTH = 10;
const CHUNK_RADIUS_LINES = 8;
const queryCache = new Map<string, CachedQuery>();

export async function retrieveVaultRag(query: string, options: VaultRagOptions = {}): Promise<RagMatch[]> {
  const prefix = queryPrefix(query);
  if (!prefix) {
    return [];
  }

  const vaultPath = options.vaultPath ?? DEFAULT_VAULT_PATH;
  const maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
  const maxMatches = options.maxMatches ?? DEFAULT_MAX_MATCHES;
  const cacheKey = `${vaultPath}:${maxBytes}:${maxMatches}:${prefix}`;
  const cached = queryCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.matches;
  }

  if (!isTauriRuntime()) {
    return [];
  }

  const search = await invoke<ToolResponse<SearchFilesResult> | SearchFilesResult>("route_tool", {
    tool: "search_files",
    payload: {
      path: vaultPath,
      query: prefix,
    },
  }).catch(() => null);

  const searchOutput = unwrapToolOutput<SearchFilesResult>(search);
  const rawMatches = searchOutput?.matches ?? [];
  const ranked = rankSearchMatches(rawMatches, prefix).slice(0, maxMatches);
  const chunks: RagMatch[] = [];
  let usedBytes = 0;

  for (const match of ranked) {
    if (!match.path) {
      continue;
    }

    const file = await readVaultFile(match.path).catch(() => null);
    const content = file?.content;
    if (!content) {
      continue;
    }

    const chunk = chunkAroundLine(content, match.line ?? 1);
    const remaining = maxBytes - usedBytes;
    if (remaining <= 0) {
      break;
    }

    const text = clampText(chunk, Math.min(remaining, Math.ceil(maxBytes / Math.max(1, maxMatches))));
    usedBytes += text.length;
    chunks.push({
      id: `vault:${match.path}:${match.line ?? 1}`,
      path: file.path ?? match.path,
      title: titleFromPath(match.path),
      text,
      keywords: [prefix],
      score: scoreMatch(match.text ?? "", prefix),
    });
  }

  queryCache.set(cacheKey, {
    expiresAt: Date.now() + (options.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS),
    matches: chunks,
  });

  return chunks;
}

export function createVaultRagRetriever(options: VaultRagOptions = {}) {
  return (query: string) => retrieveVaultRag(query, options);
}

export function queryPrefix(query: string): string {
  return query.trim().toLowerCase().replace(/\s+/g, " ").slice(0, QUERY_PREFIX_LENGTH);
}

function rankSearchMatches(matches: NonNullable<SearchFilesResult["matches"]>, prefix: string) {
  return [...matches].sort((left, right) => {
    const leftScore = scoreMatch(left.text ?? "", prefix);
    const rightScore = scoreMatch(right.text ?? "", prefix);
    return rightScore - leftScore || (left.path ?? "").localeCompare(right.path ?? "");
  });
}

function scoreMatch(text: string, prefix: string): number {
  const normalized = text.toLowerCase();
  if (normalized.startsWith(prefix)) {
    return 100;
  }
  if (normalized.includes(prefix)) {
    return 50;
  }
  return 1;
}

async function readVaultFile(path: string): Promise<ReadFileResult> {
  const result = await invoke<ToolResponse<ReadFileResult> | ReadFileResult>("route_tool", {
    tool: "read_file",
    payload: { path },
  });
  return unwrapToolOutput<ReadFileResult>(result) ?? {};
}

function unwrapToolOutput<T>(value: ToolResponse<T> | T | null): T | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  if ("output" in value) {
    return (value as ToolResponse<T>).output ?? null;
  }

  return value as T;
}

function chunkAroundLine(content: string, line: number): string {
  const lines = content.split(/\r?\n/);
  const index = Math.max(0, line - 1);
  const start = Math.max(0, index - CHUNK_RADIUS_LINES);
  const end = Math.min(lines.length, index + CHUNK_RADIUS_LINES + 1);
  return lines.slice(start, end).join("\n").trim();
}

function clampText(text: string, maxBytes: number): string {
  if (text.length <= maxBytes) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxBytes - 16)).trimEnd()}\n...[trimmed]`;
}

function titleFromPath(path: string): string {
  const file = path.split(/[\\/]/).pop() ?? path;
  return file.replace(/\.[^.]+$/, "") || path;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
