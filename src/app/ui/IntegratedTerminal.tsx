import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Circle, Play, ShieldCheck, Terminal as TerminalIcon } from "lucide-react";
import {
  createTerminalSession,
  fetchTerminalEvents,
  runTerminalCommand,
  type TerminalCommandRecord,
  type TerminalEvent,
  type TerminalSession,
} from "../core/terminal";

type IntegratedTerminalProps = {
  taskId: string;
};

export function IntegratedTerminal({ taskId }: IntegratedTerminalProps) {
  const [session, setSession] = useState<TerminalSession | null>(null);
  const [events, setEvents] = useState<TerminalEvent[]>([]);
  const [history, setHistory] = useState<TerminalCommandRecord[]>([]);
  const [command, setCommand] = useState("pwd");
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    createTerminalSession(taskId).then((nextSession) => {
      if (!cancelled) {
        setSession(nextSession);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  useEffect(() => {
    if (!session) {
      return;
    }

    const interval = window.setInterval(async () => {
      const lastEventId = events.length > 0 ? events[events.length - 1].event_id : undefined;
      const nextEvents = await fetchTerminalEvents(session.session_id, lastEventId);
      if (nextEvents.length > 0) {
        setEvents((current) => appendUniqueEvents(current, nextEvents));
      }
    }, 1200);

    return () => window.clearInterval(interval);
  }, [events, session]);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      if (scrollerRef.current) {
        scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
      }
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [events, running]);

  const outputLines = useMemo(() => renderTerminalLines(events), [events]);

  async function submitCommand(event?: FormEvent) {
    event?.preventDefault();
    const nextCommand = command.trim();
    if (!session || !nextCommand || running) {
      return;
    }

    setRunning(true);
    setCommand("");
    setHistoryIndex(null);
    const result = await runTerminalCommand(session.session_id, nextCommand);
    setHistory((current) => [...current, result.command]);
    setEvents((current) => appendUniqueEvents(current, result.events));
    setRunning(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      const nextIndex = historyIndex === null ? history.length - 1 : Math.max(0, historyIndex - 1);
      const entry = history[nextIndex];
      if (entry) {
        setHistoryIndex(nextIndex);
        setCommand(entry.command);
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (historyIndex === null) {
        return;
      }
      const nextIndex = historyIndex + 1;
      const entry = history[nextIndex];
      if (entry) {
        setHistoryIndex(nextIndex);
        setCommand(entry.command);
      } else {
        setHistoryIndex(null);
        setCommand("");
      }
    }
  }

  return (
    <section className="flex min-h-[260px] flex-col border-t border-neutral-800 bg-[#090909]">
      <header className="flex h-10 items-center justify-between border-b border-neutral-800 px-4">
        <div className="flex items-center gap-2">
          <TerminalIcon size={15} className="text-neutral-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-300">Terminal</h3>
          <span className="rounded border border-neutral-800 px-2 py-0.5 text-[11px] text-neutral-500">
            {session?.sandbox_id ?? "starting"}
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-neutral-500">
          <ShieldCheck size={14} className="text-emerald-400" />
          <span>Sandboxed</span>
          <Circle size={8} className={running ? "fill-amber-300 text-amber-300" : "fill-emerald-400 text-emerald-400"} />
        </div>
      </header>

      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-auto px-4 py-3 font-mono text-[12px] leading-5">
        {outputLines.length === 0 ? (
          <div className="text-neutral-600">Command output and task execution logs stream here.</div>
        ) : (
          outputLines.map((line) => (
            <div key={line.id} className={line.tone}>
              {line.text}
            </div>
          ))
        )}
        {running && <div className="text-amber-300">command running...</div>}
      </div>

      <form onSubmit={submitCommand} className="flex items-center gap-2 border-t border-neutral-800 px-3 py-2">
        <span className="font-mono text-xs text-emerald-400">$</span>
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!session || running}
          className="h-9 min-w-0 flex-1 rounded border border-neutral-800 bg-neutral-950 px-3 font-mono text-xs text-neutral-100 outline-none transition placeholder:text-neutral-700 focus:border-neutral-600 disabled:opacity-50"
          placeholder="Run sandboxed command..."
        />
        <button
          type="submit"
          disabled={!session || !command.trim() || running}
          className="flex h-9 items-center gap-2 rounded border border-neutral-700 bg-neutral-900 px-3 text-xs font-medium text-neutral-200 transition hover:border-neutral-600 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play size={13} />
          Run
        </button>
      </form>
    </section>
  );
}

function appendUniqueEvents(current: TerminalEvent[], incoming: TerminalEvent[]): TerminalEvent[] {
  const seen = new Set(current.map((event) => event.event_id));
  const next = [...current];
  for (const event of incoming) {
    if (!seen.has(event.event_id)) {
      next.push(event);
      seen.add(event.event_id);
    }
  }
  return next;
}

function renderTerminalLines(events: TerminalEvent[]): Array<{ id: string; text: string; tone: string }> {
  return events.flatMap((event) => {
    if (event.event_type === "command_started") {
      return [{
        id: event.event_id,
        text: `$ ${String(event.payload.command ?? "")}`,
        tone: "text-neutral-300",
      }];
    }
    if (event.event_type === "output") {
      return String(event.payload.text ?? "")
        .split("\n")
        .filter(Boolean)
        .map((text, index) => ({
          id: `${event.event_id}-${index}`,
          text,
          tone: "whitespace-pre-wrap text-neutral-400",
        }));
    }
    if (event.event_type === "command_denied") {
      return [{
        id: event.event_id,
        text: `denied: ${String(event.payload.reason ?? event.payload.text ?? "permission denied")}`,
        tone: "text-red-300",
      }];
    }
    if (event.event_type === "command_completed") {
      return [{
        id: event.event_id,
        text: `exit ${String(event.payload.code ?? "unknown")}`,
        tone: event.payload.success ? "text-emerald-400" : "text-red-300",
      }];
    }
    return [];
  });
}
