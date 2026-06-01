import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { chat, listNotes, NoteSummary, RagChunk, readNote, writeNote } from "./api";
import "./styles.css";

type ServiceStatus = {
  name: string;
  label: string;
  status: "running" | "stopped" | string;
  detail: string;
  pid?: number | null;
  restart_count?: number;
  last_failure?: string | null;
  heartbeat_age_ms?: number | null;
};

type LauncherStatus = {
  services: ServiceStatus[];
  running: boolean;
  healthy: boolean;
};

type LogLine = {
  service: string;
  stream: string;
  line: string;
};

type WatchdogEvent = {
  service: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
  restart_count: number;
};

const emptyLauncher: LauncherStatus = {
  services: [
    { name: "backend", label: "Backend API", status: "stopped", detail: "Waiting for status" },
    { name: "rag", label: "RAG / Qdrant", status: "stopped", detail: "Waiting for status" },
    { name: "agent", label: "Agent Swarm", status: "stopped", detail: "Waiting for status" },
    { name: "memory", label: "Memory System", status: "stopped", detail: "Waiting for status" },
    { name: "frontend", label: "Desktop Frontend", status: "running", detail: "Tauri dashboard loaded" }
  ],
  running: false,
  healthy: false
};

async function launcherInvoke<T>(command: string): Promise<T> {
  return invoke<T>(command);
}

function App() {
  const [launcher, setLauncher] = useState<LauncherStatus>(emptyLauncher);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [launcherBusy, setLauncherBusy] = useState(false);
  const [launcherError, setLauncherError] = useState("");
  const [watchdogAlert, setWatchdogAlert] = useState<WatchdogEvent | null>(null);
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [activePath, setActivePath] = useState("");
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [message, setMessage] = useState("");
  const [answer, setAnswer] = useState("");
  const [chunks, setChunks] = useState<RagChunk[]>([]);
  const [status, setStatus] = useState("Ready");
  const [selectedText, setSelectedText] = useState("");
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const dirty = content !== savedContent;
  const runningCount = launcher.services.filter((service) => service.status === "running").length;

  const servicesByName = useMemo(
    () => Object.fromEntries(launcher.services.map((service) => [service.name, service])),
    [launcher.services]
  );

  useEffect(() => {
    refreshLauncher();
    launcherInvoke<LogLine[]>("get_anubis_logs")
      .then(setLogs)
      .catch(() => setLogs([]));
    const timer = window.setInterval(refreshLauncher, 2500);
    let unlisten: (() => void) | undefined;
    let unlistenWatchdog: (() => void) | undefined;
    listen<LogLine>("anubis-log", (event) => {
      setLogs((current) => [...current.slice(-799), event.payload]);
    }).then((dispose) => {
      unlisten = dispose;
    });
    listen<WatchdogEvent>("anubis-watchdog", (event) => {
      setWatchdogAlert(event.payload);
      refreshLauncher();
    }).then((dispose) => {
      unlistenWatchdog = dispose;
    });
    return () => {
      window.clearInterval(timer);
      unlisten?.();
      unlistenWatchdog?.();
    };
  }, []);

  useEffect(() => {
    listNotes().then(setNotes).catch(() => setNotes([]));
  }, [servicesByName.backend?.status]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "end" });
  }, [logs]);

  async function refreshLauncher() {
    try {
      const next = await launcherInvoke<LauncherStatus>("get_anubis_status");
      setLauncher(next);
    } catch (error) {
      setLauncherError(String(error));
    }
  }

  async function runLauncherCommand(command: "start_anubis" | "stop_anubis" | "restart_anubis") {
    setLauncherBusy(true);
    setLauncherError("");
    try {
      const next = await launcherInvoke<LauncherStatus>(command);
      setLauncher(next);
      if (command !== "stop_anubis") {
        listNotes().then(setNotes).catch(() => setNotes([]));
      }
    } catch (error) {
      setLauncherError(String(error));
    } finally {
      setLauncherBusy(false);
      refreshLauncher();
    }
  }

  async function openNote(path: string) {
    setStatus("Opening note");
    const note = await readNote(path);
    setActivePath(note.path);
    setContent(note.content);
    setSavedContent(note.content);
    setStatus("Ready");
  }

  async function saveActiveNote() {
    if (!activePath) return;
    setStatus("Saving");
    await writeNote(activePath, content);
    setSavedContent(content);
    setStatus("Saved");
  }

  async function sendMessage() {
    if (!message.trim()) return;
    setStatus("Querying RAG");
    const result = await chat(message);
    setAnswer(result.answer);
    setChunks(result.chunks_used);
    setStatus("Ready");
  }

  async function injectSelection() {
    const text = selectedText.trim();
    if (!text) return;
    setMessage(`remember: ${text}`);
    setStatus("Injecting memory");
    const result = await chat(`remember: ${text}`);
    setAnswer(result.answer);
    setChunks(result.chunks_used);
    setStatus("Memory injected");
  }

  function handleEditorSelect(event: React.SyntheticEvent<HTMLTextAreaElement>) {
    const target = event.currentTarget;
    setSelectedText(target.value.slice(target.selectionStart, target.selectionEnd));
  }

  return (
    <main className="app-shell">
      <section className="launcher-panel">
        <header className="launcher-header">
          <div>
            <h1>Anubis Desktop OS</h1>
            <span>
              {launcher.healthy
                ? "System healthy"
                : launcher.running
                  ? "Services starting or partially available"
                  : "System stopped"}
              {" · "}
              {runningCount}/{launcher.services.length} services running
            </span>
          </div>
          <div className="launcher-actions">
            <button disabled={launcherBusy} onClick={() => runLauncherCommand("start_anubis")}>
              Start Anubis
            </button>
            <button disabled={launcherBusy} onClick={() => runLauncherCommand("stop_anubis")}>
              Stop Anubis
            </button>
            <button disabled={launcherBusy} onClick={() => runLauncherCommand("restart_anubis")}>
              Restart
            </button>
          </div>
        </header>

        <div className="status-grid">
          {launcher.services.map((service) => (
            <article className={`status-tile ${service.status === "running" ? "is-running" : ""}`} key={service.name}>
              <div>
                <strong>{service.label}</strong>
                <span className={service.status === "running" ? "status-dot running" : "status-dot"} />
              </div>
              <p>{service.status}</p>
              <small>
                {service.detail}
                {service.pid ? ` · pid ${service.pid}` : ""}
                {service.restart_count ? ` · restarts ${service.restart_count}` : ""}
                {service.heartbeat_age_ms ? ` · heartbeat ${Math.round(service.heartbeat_age_ms / 1000)}s` : ""}
              </small>
              {service.last_failure ? <small className="failure-detail">{service.last_failure}</small> : null}
            </article>
          ))}
        </div>

        {launcherError ? <p className="launcher-error">{launcherError}</p> : null}
        {watchdogAlert ? (
          <p className={`watchdog-alert ${watchdogAlert.severity}`}>
            Watchdog: {watchdogAlert.service} · {watchdogAlert.message}
            {watchdogAlert.restart_count ? ` · restart ${watchdogAlert.restart_count}` : ""}
          </p>
        ) : null}

        <section className="logs-panel">
          <div className="logs-header">
            <strong>Live Logs</strong>
            <button onClick={() => setLogs([])}>Clear</button>
          </div>
          <div className="logs-stream" aria-label="Anubis service logs">
            {logs.length === 0 ? (
              <p className="empty">No launcher logs yet.</p>
            ) : (
              logs.map((entry, index) => (
                <pre className={`log-line ${entry.stream}`} key={`${entry.service}-${index}`}>
                  <span>[{entry.service}:{entry.stream}]</span> {entry.line}
                </pre>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </section>
      </section>

      <section className="workspace-shell">
        <aside className="vault-pane">
          <header className="pane-header">
            <div>
              <h2>Vault</h2>
              <span>Markdown memory</span>
            </div>
            <button className="icon-button" title="Refresh notes" onClick={() => listNotes().then(setNotes)}>
              R
            </button>
          </header>
          <nav className="note-list" aria-label="Markdown notes">
            {notes.map((note) => (
              <button
                className={note.path === activePath ? "note active" : "note"}
                draggable
                key={note.path}
                onClick={() => openNote(note.path)}
                onDragStart={(event) => event.dataTransfer.setData("text/plain", note.path)}
              >
                <span>{note.title}</span>
                <small>{note.path}</small>
              </button>
            ))}
          </nav>
        </aside>

        <section className="editor-pane">
          <header className="editor-bar">
            <div>
              <strong>{activePath || "No note selected"}</strong>
              <span>{dirty ? "Unsaved changes" : status}</span>
            </div>
            <div className="actions">
              <button onClick={injectSelection} disabled={!selectedText.trim()}>
                Inject selection
              </button>
              <button onClick={saveActiveNote} disabled={!activePath || !dirty}>
                Save
              </button>
            </div>
          </header>
          <textarea
            className="markdown-editor"
            placeholder="Open a Markdown note from the vault."
            value={content}
            onChange={(event) => setContent(event.target.value)}
            onSelect={handleEditorSelect}
            onDrop={(event) => {
              const path = event.dataTransfer.getData("text/plain");
              if (path.endsWith(".md")) openNote(path);
            }}
          />
        </section>

        <aside className="agent-pane">
          <header className="pane-header">
            <div>
              <h2>Agent</h2>
              <span>Chat + RAG insights</span>
            </div>
          </header>
          <section className="chat-box">
            <textarea
              placeholder="Ask Anubis. RAG is checked before answering."
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) sendMessage();
              }}
            />
            <button onClick={sendMessage}>Send</button>
          </section>
          <section className="answer">
            <h3>Answer</h3>
            <p>{answer || "No response yet."}</p>
          </section>
          <section className="rag-panel">
            <h3>Sources</h3>
            {chunks.length === 0 ? (
              <p className="empty">No chunks used yet.</p>
            ) : (
              chunks.map((chunk, index) => (
                <article className="chunk" key={`${chunk.path}-${chunk.id}-${index}`}>
                  <div>
                    <strong>{chunk.heading || "Markdown chunk"}</strong>
                    <span>{typeof chunk.score === "number" ? chunk.score.toFixed(3) : "n/a"}</span>
                  </div>
                  <small>
                    {chunk.path} {chunk.line_start ? `:${chunk.line_start}-${chunk.line_end}` : ""}
                  </small>
                  <p>{chunk.text}</p>
                </article>
              ))
            )}
          </section>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
