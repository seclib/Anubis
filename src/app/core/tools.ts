import { invoke } from "@tauri-apps/api/core";

export type ToolCall = {
  name: string;
  payload: Record<string, unknown>;
};

export type ToolResult = {
  tool: string;
  status: "ok" | "error";
  output: unknown;
  durationMs?: number;
};

type TauriToolResponse = {
  tool: string;
  status: "ok" | "error";
  output: unknown;
  durationMs: number;
};

const TOOL_TAG_PATTERN = /<tool>([\s\S]*?)<\/tool>/gi;
const ALLOWED_TOOLS = new Set(["read_file", "write_file", "search_files", "run_shell", "git", "git_status", "git_diff", "git_log"]);
const ALLOWED_COMMANDS = new Set(["rg", "grep", "ls", "pwd", "sed", "cat", "head", "tail", "wc"]);
const BLOCKED_TOKENS = new Set([
  "rm",
  "sudo",
  "su",
  "curl",
  "wget",
  "chmod",
  "chown",
  "mkfs",
  "dd",
  "nc",
  "netcat",
  "ssh",
  "scp",
  "eval",
  "source",
  "bash",
  "sh",
  "zsh",
  "fish",
  "powershell",
]);
const BLOCKED_PATTERNS = ["&&", "||", "|", ";", "`", "$(", ">", "<", "\n", "\r", "*", "~"];
const MAX_TIMEOUT_MS = 30_000;
const MAX_WRITE_CHARS = 512 * 1024;

export function detectToolCalls(text: string): ToolCall[] {
  const calls: ToolCall[] = [];
  let match: RegExpExecArray | null;

  while ((match = TOOL_TAG_PATTERN.exec(text)) !== null) {
    const parsed = parseToolJson(match[1]);
    if (parsed) {
      calls.push(parsed);
    }
  }

  const direct = parseToolJson(text.trim());
  if (direct) {
    calls.push(direct);
  }

  return dedupeToolCalls(calls);
}

export function stripToolMarkup(text: string): string {
  const stripped = text.replace(TOOL_TAG_PATTERN, "").trim();
  return parseToolJson(stripped) ? "" : stripped;
}

export async function executeToolCall(call: ToolCall): Promise<ToolResult> {
  const validationError = validateToolCall(call);
  if (validationError) {
    return {
      tool: call.name,
      status: "error",
      output: validationError,
    };
  }

  if (!isTauriRuntime()) {
    return {
      tool: call.name,
      status: "error",
      output: "Tool execution requires the Tauri runtime",
    };
  }

  try {
    const response = await invoke<TauriToolResponse>("route_tool", {
      tool: call.name,
      payload: call.payload,
    });

    return {
      tool: response.tool,
      status: response.status,
      output: response.output,
      durationMs: response.durationMs,
    };
  } catch (error) {
    return {
      tool: call.name,
      status: "error",
      output: error instanceof Error ? error.message : String(error),
    };
  }
}

export function validateToolCall(call: ToolCall): string | null {
  if (!ALLOWED_TOOLS.has(call.name)) {
    return `Tool is not allowed: ${call.name}`;
  }

  if (!isRecord(call.payload)) {
    return "Tool payload must be an object";
  }

  switch (call.name) {
    case "read_file":
      return validatePathPayload(call.payload, "path");
    case "write_file":
      return validateWritePayload(call.payload);
    case "search_files":
      return validateSearchPayload(call.payload);
    case "run_shell":
      return validateShellPayload(call.payload);
    case "git":
    case "git_status":
    case "git_diff":
    case "git_log":
      return validateGitPayload(call.payload);
    default:
      return `Tool is not allowed: ${call.name}`;
  }
}

function validateWritePayload(payload: Record<string, unknown>): string | null {
  const pathError = validatePathPayload(payload, "path");
  if (pathError) {
    return pathError;
  }

  const content = payload.content;
  if (typeof content !== "string") {
    return "write_file requires string payload.content";
  }
  if (content.length > MAX_WRITE_CHARS) {
    return `write_file content exceeds ${MAX_WRITE_CHARS} characters`;
  }
  return null;
}

function validateSearchPayload(payload: Record<string, unknown>): string | null {
  const query = payload.query;
  if (typeof query !== "string" || query.trim().length < 2) {
    return "search_files requires payload.query with at least 2 characters";
  }

  return payload.path === undefined ? null : validatePathPayload(payload, "path");
}

function validateShellPayload(payload: Record<string, unknown>): string | null {
  const argv = commandArgv(payload);
  if (typeof argv === "string") {
    return argv;
  }
  if (argv.length === 0) {
    return "run_shell requires a command or argv";
  }

  const program = argv[0];
  if (!ALLOWED_COMMANDS.has(program)) {
    return `Command is not allowed: ${program}`;
  }

  for (const arg of argv) {
    const lower = arg.toLowerCase();
    if (BLOCKED_TOKENS.has(lower)) {
      return `Blocked command token: ${arg}`;
    }
    if (BLOCKED_PATTERNS.some((pattern) => arg.includes(pattern))) {
      return `Blocked shell syntax in argument: ${arg}`;
    }
    if (isUnsafePath(arg)) {
      return `Path escapes are not allowed in shell arguments: ${arg}`;
    }
  }

  if (program === "sed" && argv.some((arg) => arg === "-i" || arg.startsWith("-i"))) {
    return "run_shell cannot mutate files with sed -i; use write_file instead";
  }

  const timeoutMs = payload.timeoutMs;
  if (timeoutMs !== undefined && (!Number.isInteger(timeoutMs) || Number(timeoutMs) < 1 || Number(timeoutMs) > MAX_TIMEOUT_MS)) {
    return `timeoutMs must be between 1 and ${MAX_TIMEOUT_MS}`;
  }

  return null;
}

function validateGitPayload(payload: Record<string, unknown>): string | null {
  const operation = payload.operation;
  if (operation !== undefined && typeof operation !== "string") {
    return "git operation must be a string";
  }

  if (typeof operation === "string" && !["status", "diff", "log", "branch", "show"].includes(operation)) {
    return `Unsupported git operation: ${operation}`;
  }

  const rev = payload.rev;
  if (rev !== undefined && (typeof rev !== "string" || !/^[A-Za-z0-9_./-]+$/.test(rev))) {
    return "Invalid git revision";
  }

  return validateOptionalTimeout(payload);
}

function validatePathPayload(payload: Record<string, unknown>, key: string): string | null {
  const path = payload[key];
  if (typeof path !== "string" || !path.trim()) {
    return `Tool requires string payload.${key}`;
  }
  if (isUnsafePath(path)) {
    return `Path escapes project sandbox: ${path}`;
  }
  return null;
}

function validateOptionalTimeout(payload: Record<string, unknown>): string | null {
  const timeoutMs = payload.timeoutMs;
  if (timeoutMs !== undefined && (!Number.isInteger(timeoutMs) || Number(timeoutMs) < 1 || Number(timeoutMs) > MAX_TIMEOUT_MS)) {
    return `timeoutMs must be between 1 and ${MAX_TIMEOUT_MS}`;
  }
  return null;
}

function commandArgv(payload: Record<string, unknown>): string[] | string {
  if (Array.isArray(payload.argv)) {
    return payload.argv.every((item) => typeof item === "string") ? payload.argv : "argv must contain only strings";
  }

  const command = payload.command;
  if (typeof command !== "string" || !command.trim()) {
    return "run_shell requires string payload.command or string[] payload.argv";
  }

  if (BLOCKED_PATTERNS.some((pattern) => command.includes(pattern))) {
    return "run_shell command contains blocked shell syntax";
  }

  return command.trim().split(/\s+/);
}

function parseToolJson(raw: string): ToolCall | null {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
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

function isUnsafePath(value: string): boolean {
  return (
    value.trim() === "" ||
    value.startsWith("/") ||
    /^[A-Za-z]:[\\/]/.test(value) ||
    value === ".." ||
    value.startsWith("../") ||
    value.includes("/../") ||
    value.includes("\\..\\") ||
    value.endsWith("/..") ||
    value.endsWith("\\..")
  );
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
