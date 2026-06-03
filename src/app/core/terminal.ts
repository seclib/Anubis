export type TerminalEventType =
  | "session_created"
  | "command_started"
  | "output"
  | "command_completed"
  | "command_denied";

export type TerminalEvent = {
  event_id: string;
  session_id: string;
  task_id: string;
  event_type: TerminalEventType;
  payload: Record<string, unknown>;
  created_at: string;
};

export type TerminalCommandRecord = {
  command_id: string;
  command: string;
  success: boolean;
  output: string;
  code: number | null;
  started_at: string;
  completed_at: string;
  permission: Record<string, unknown>;
};

export type TerminalSession = {
  session_id: string;
  task_id: string;
  sandbox_id: string;
  workspace: string;
  agent_type: "executor" | "planner" | "reviewer";
  created_at: string;
};

export type TerminalSnapshot = {
  session: TerminalSession;
  history: TerminalCommandRecord[];
  events: TerminalEvent[];
};

export type TerminalCommandResult = {
  session: TerminalSession;
  command: TerminalCommandRecord;
  events: TerminalEvent[];
};

export async function createTerminalSession(taskId: string): Promise<TerminalSession> {
  try {
    const response = await fetch("/api/terminal/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, agent_type: "executor" }),
    });
    if (response.ok) {
      const data = (await response.json()) as { session?: TerminalSession } | TerminalSession;
      return "session" in data && data.session ? data.session : data as TerminalSession;
    }
  } catch {
    return demoSession(taskId);
  }

  return demoSession(taskId);
}

export async function runTerminalCommand(sessionId: string, command: string): Promise<TerminalCommandResult> {
  try {
    const response = await fetch(`/api/terminal/sessions/${encodeURIComponent(sessionId)}/commands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    if (response.ok) {
      return (await response.json()) as TerminalCommandResult;
    }
  } catch {
    return demoCommand(sessionId, command);
  }

  return demoCommand(sessionId, command);
}

export async function fetchTerminalEvents(sessionId: string, afterEventId?: string): Promise<TerminalEvent[]> {
  const suffix = afterEventId ? `?after_event_id=${encodeURIComponent(afterEventId)}` : "";
  try {
    const response = await fetch(`/api/terminal/sessions/${encodeURIComponent(sessionId)}/events${suffix}`);
    if (response.ok) {
      const data = (await response.json()) as { events?: TerminalEvent[] } | TerminalEvent[];
      return Array.isArray(data) ? data : data.events ?? [];
    }
  } catch {
    return [];
  }

  return [];
}

function demoSession(taskId: string): TerminalSession {
  return {
    session_id: "terminal-demo",
    task_id: taskId,
    sandbox_id: "sandbox-demo",
    workspace: "/workspace/demo",
    agent_type: "executor",
    created_at: new Date().toISOString(),
  };
}

function demoCommand(sessionId: string, command: string): TerminalCommandResult {
  const now = new Date().toISOString();
  const taskId = "task-demo";
  const session = demoSession(taskId);
  const commandRecord: TerminalCommandRecord = {
    command_id: crypto.randomUUID(),
    command,
    success: !command.includes("&&"),
    output: command.includes("&&")
      ? "permission denied: shell control or expansion is not allowed"
      : `$ ${command}\nSandbox output stream unavailable; backend terminal service will provide live logs.`,
    code: command.includes("&&") ? 1 : 0,
    started_at: now,
    completed_at: now,
    permission: { status: command.includes("&&") ? "denied" : "approved", tool: "run_command" },
  };
  return {
    session: { ...session, session_id: sessionId },
    command: commandRecord,
    events: [
      event(sessionId, taskId, "command_started", { command_id: commandRecord.command_id, command }),
      event(sessionId, taskId, commandRecord.success ? "output" : "command_denied", {
        command_id: commandRecord.command_id,
        text: commandRecord.output,
      }),
      event(sessionId, taskId, "command_completed", {
        command_id: commandRecord.command_id,
        success: commandRecord.success,
        code: commandRecord.code,
      }),
    ],
  };
}

function event(
  sessionId: string,
  taskId: string,
  eventType: TerminalEventType,
  payload: Record<string, unknown>,
): TerminalEvent {
  return {
    event_id: crypto.randomUUID(),
    session_id: sessionId,
    task_id: taskId,
    event_type: eventType,
    payload,
    created_at: new Date().toISOString(),
  };
}
