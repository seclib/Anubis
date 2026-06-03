import { invoke } from "@tauri-apps/api/core";
import type { RagMatch } from "./agent";

export type LightRagOptions = {
  sources?: string[];
  maxContextChars?: number;
  maxMatches?: number;
  maxSearchTerms?: number;
  cacheTtlMs?: number;
};

export type VaultRagOptions = {
  vaultPath?: string;
  maxBytes?: number;
  maxMatches?: number;
  cacheTtlMs?: number;
};

type SearchFilesResult = {
  matches?: SearchFileMatch[];
};

type SearchFileMatch = {
  path?: string;
  line?: number;
  text?: string;
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

const DEFAULT_SOURCES = ["vault", "memory", "vault/memory"];
const DEFAULT_MAX_CONTEXT_CHARS = 2_000;
const DEFAULT_MAX_MATCHES = 5;
const DEFAULT_MAX_SEARCH_TERMS = 4;
const DEFAULT_CACHE_TTL_MS = 20_000;
const QUERY_PREFIX_LENGTH = 10;
const CHUNK_RADIUS_LINES = 6;
const queryCache = new Map<string, CachedQuery>();

const STOP_WORDS = new Set([
  "about",
  "after",
  "again",
  "also",
  "and",
  "are",
  "can",
  "could",
  "from",
  "have",
  "into",
  "show",
  "that",
  "the",
  "this",
  "what",
  "when",
  "where",
  "with",
  "your",
]);

export async function retrieveLightRag(
  query: string,
  options: LightRagOptions = {},
  signal?: AbortSignal,
): Promise<RagMatch[]> {
  const terms = searchTerms(query, options.maxSearchTerms ?? DEFAULT_MAX_SEARCH_TERMS);
  if (!terms.length || !isTauriRuntime()) {
    return [];
  }

  const sources = uniqueSources(options.sources ?? DEFAULT_SOURCES);
  const maxMatches = options.maxMatches ?? DEFAULT_MAX_MATCHES;
  const maxContextChars = options.maxContextChars ?? DEFAULT_MAX_CONTEXT_CHARS;
  const cacheKey = JSON.stringify({ sources, terms, maxMatches, maxContextChars });
  const cached = queryCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.matches;
  }

  const rawMatches: SearchFileMatch[] = [];
  for (const source of sources) {
    for (const term of terms) {
      if (signal?.aborted) {
        return [];
      }
      rawMatches.push(...(await searchSource(source, term)));
    }
  }

  const ranked = rankSearchMatches(dedupeSearchMatches(rawMatches), query).slice(0, maxMatches * 2);
  const matches = await buildRagMatches(ranked, query, maxMatches, maxContextChars, signal);

  queryCache.set(cacheKey, {
    expiresAt: Date.now() + (options.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS),
    matches,
  });

  return matches;
}

export function formatRagContext(matches: RagMatch[], maxChars = DEFAULT_MAX_CONTEXT_CHARS): string {
  if (!matches.length) {
    return "";
  }

  return clampText(
    [
      "Local context:",
      ...matches.map((match, index) => {
        const label = match.path || match.title || match.id;
        return `[${index + 1}] ${label}\n${clampText(match.text, 520)}`;
      }),
    ].join("\n\n"),
    maxChars,
  );
}

export async function retrieveVaultRag(query: string, options: VaultRagOptions = {}): Promise<RagMatch[]> {
  return retrieveLightRag(query, {
    sources: [options.vaultPath ?? "vault"],
    maxContextChars: options.maxBytes ?? DEFAULT_MAX_CONTEXT_CHARS,
    maxMatches: options.maxMatches,
    cacheTtlMs: options.cacheTtlMs,
  });
}

export function createVaultRagRetriever(options: VaultRagOptions = {}) {
  return (query: string, signal?: AbortSignal) =>
    retrieveLightRag(
      query,
      {
        sources: [options.vaultPath ?? "vault"],
        maxContextChars: options.maxBytes ?? DEFAULT_MAX_CONTEXT_CHARS,
        maxMatches: options.maxMatches,
        cacheTtlMs: options.cacheTtlMs,
      },
      signal,
    );
}

export function queryPrefix(query: string): string {
  return query.trim().toLowerCase().replace(/\s+/g, " ").slice(0, QUERY_PREFIX_LENGTH);
}

async function buildRagMatches(
  matches: SearchFileMatch[],
  query: string,
  maxMatches: number,
  maxContextChars: number,
  signal?: AbortSignal,
): Promise<RagMatch[]> {
  const chunks: RagMatch[] = [];
  let remainingChars = maxContextChars;

  for (const match of matches) {
    if (signal?.aborted || remainingChars <= 0 || chunks.length >= maxMatches || !match.path) {
      break;
    }

    const file = await readFile(match.path).catch(() => null);
    if (!file?.content) {
      continue;
    }

    const chunk = chunkAroundLine(file.content, match.line ?? 1);
    const text = clampText(chunk, Math.min(remainingChars, Math.ceil(maxContextChars / maxMatches)));
    if (!text) {
      continue;
    }

    remainingChars -= text.length;
    chunks.push({
      id: `rag:${match.path}:${match.line ?? 1}`,
      path: file.path ?? match.path,
      title: titleFromPath(match.path),
      text,
      keywords: searchTerms(query, 8),
      score: scoreText([match.text, chunk, match.path].filter(Boolean).join("\n"), query),
    });
  }

  return chunks.sort((left, right) => right.score - left.score);
}

async function searchSource(source: string, query: string): Promise<SearchFileMatch[]> {
  const response = await invoke<ToolResponse<SearchFilesResult> | SearchFilesResult>("route_tool", {
    tool: "search_files",
    payload: {
      path: source,
      query,
    },
  }).catch(() => null);

  return unwrapToolOutput<SearchFilesResult>(response)?.matches ?? [];
}

async function readFile(path: string): Promise<ReadFileResult> {
  const response = await invoke<ToolResponse<ReadFileResult> | ReadFileResult>("route_tool", {
    tool: "read_file",
    payload: { path },
  });
  return unwrapToolOutput<ReadFileResult>(response) ?? {};
}

function rankSearchMatches(matches: SearchFileMatch[], query: string): SearchFileMatch[] {
  return [...matches].sort((left, right) => {
    const rightScore = scoreText([right.path, right.text].filter(Boolean).join("\n"), query);
    const leftScore = scoreText([left.path, left.text].filter(Boolean).join("\n"), query);
    return rightScore - leftScore || (left.path ?? "").localeCompare(right.path ?? "");
  });
}

function dedupeSearchMatches(matches: SearchFileMatch[]): SearchFileMatch[] {
  const seen = new Set<string>();
  const deduped: SearchFileMatch[] = [];

  for (const match of matches) {
    const key = `${match.path ?? ""}:${match.line ?? 0}`;
    if (!match.path || seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(match);
  }

  return deduped;
}

function scoreText(text: string, query: string): number {
  const normalized = text.toLowerCase();
  return searchTerms(query, 8).reduce((score, term) => {
    if (normalized.includes(term)) {
      return score + (normalized.startsWith(term) ? 8 : 4);
    }
    return score;
  }, 0);
}

function searchTerms(query: string, limit: number): string[] {
  const prefix = queryPrefix(query);
  const tokens =
    query
      .toLowerCase()
      .match(/[a-z0-9_./-]{3,}/g)
      ?.filter((token) => !STOP_WORDS.has(token)) ?? [];

  return [...new Set([prefix, ...tokens])]
    .filter((term) => term.length >= 2)
    .sort((left, right) => right.length - left.length)
    .slice(0, limit);
}

function uniqueSources(sources: string[]): string[] {
  return [...new Set(sources.map((source) => trimSlashes(source)).filter(Boolean))];
}

function chunkAroundLine(content: string, line: number): string {
  const lines = content.split(/\r?\n/);
  const index = Math.max(0, line - 1);
  const start = Math.max(0, index - CHUNK_RADIUS_LINES);
  const end = Math.min(lines.length, index + CHUNK_RADIUS_LINES + 1);
  return lines.slice(start, end).join("\n").trim();
}

function clampText(text: string, maxChars: number): string {
  const compact = text.replace(/\n{3,}/g, "\n\n").trim();
  if (compact.length <= maxChars) {
    return compact;
  }
  return `${compact.slice(0, Math.max(0, maxChars - 14)).trimEnd()}\n...[trimmed]`;
}

function titleFromPath(path: string): string {
  const file = path.split(/[\\/]/).pop() ?? path;
  return file.replace(/\.[^.]+$/, "") || path;
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

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function trimSlashes(value: string): string {
  return value.replace(/^\/+|\/+$/g, "");
}
