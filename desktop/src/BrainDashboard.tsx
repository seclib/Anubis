import { useEffect, useMemo, useState } from "react";
import { BrainLogEntry, BrainSnapshot, openBrainUpdates, readBrainSnapshot } from "./api";
import { CognitiveGraphView } from "./CognitiveGraphView";

type ServiceStatus = {
  name: string;
  label: string;
  status: string;
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

type LauncherLogLine = {
  service: string;
  stream: string;
  line: string;
};

type BrainDashboardProps = {
  launcher: LauncherStatus;
  launcherLogs: LauncherLogLine[];
};

const emptySnapshot: BrainSnapshot = {
  timestamp: 0,
  system_health: {
    backend: { status: "unknown", detail: "Waiting for backend snapshot" },
    qdrant: { status: "unknown", detail: "Waiting for backend snapshot" },
    agent: { status: "unknown", detail: "Waiting for backend snapshot" },
    launcher: { status: "unknown", detail: "Waiting for launcher state" }
  },
  memory: {
    vault: { path: "", size_bytes: 0, updated_at: null },
    notes: 0,
    skills: 0,
    chunks: 0,
    embeddings: 0,
    qdrant: {
      status: "unknown",
      detail: "Waiting for Qdrant check",
      url: "",
      collection: "",
      embedding_count: 0
    }
  },
  agent_activity: {
    active_agents: [],
    current_tasks: [],
    last_executions: []
  },
  logs: [],
  architecture: {
    frontend: "React desktop dashboard",
    backend: "FastAPI brain endpoints",
    live_updates: "WebSocket /brain/ws",
    modules: []
  }
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(timestamp?: number | null): string {
  if (!timestamp) return "n/a";
  return new Date(timestamp * 1000).toLocaleTimeString();
}

function statusClass(status: string): string {
  return ["running", "ready", "observed-by-frontend"].includes(status) ? "ok" : "warn";
}

function StatTile({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <article className="brain-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function HealthPanel({ snapshot, launcher }: { snapshot: BrainSnapshot; launcher: LauncherStatus }) {
  const launcherStatus = launcher.healthy ? "running" : launcher.running ? "partial" : "stopped";
  const health = {
    ...snapshot.system_health,
    launcher: {
      status: launcherStatus,
      detail: launcher.services.map((service) => `${service.name}:${service.status}`).join("  ")
    }
  };

  return (
    <section className="brain-panel">
      <header>
        <h2>System Health</h2>
        <span>Backend, Qdrant, agents, and launcher</span>
      </header>
      <div className="brain-health-grid">
        {Object.entries(health).map(([name, status]) => (
          <article className="brain-health" key={name}>
            <div>
              <strong>{name}</strong>
              <span className={`brain-led ${statusClass(status.status)}`} />
            </div>
            <p>{status.status}</p>
            <small>{status.detail}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function MemoryPanel({ snapshot }: { snapshot: BrainSnapshot }) {
  const memory = snapshot.memory;
  return (
    <section className="brain-panel">
      <header>
        <h2>Memory Overview</h2>
        <span>{memory.vault.path || "Vault path pending"}</span>
      </header>
      <div className="brain-stat-grid">
        <StatTile label="Vault" value={formatBytes(memory.vault.size_bytes)} detail={`Updated ${formatTime(memory.vault.updated_at)}`} />
        <StatTile label="Notes" value={memory.notes} detail="Markdown notes" />
        <StatTile label="Skills" value={memory.skills} detail="Skill definitions" />
        <StatTile label="Chunks" value={memory.chunks} detail="Chunked memory sections" />
        <StatTile label="Embeddings" value={memory.embeddings} detail={memory.qdrant.collection || "Qdrant collection"} />
      </div>
    </section>
  );
}

function AgentPanel({ snapshot }: { snapshot: BrainSnapshot }) {
  const agents = snapshot.agent_activity.active_agents;
  const executions = snapshot.agent_activity.last_executions;
  return (
    <section className="brain-panel brain-agent-panel">
      <header>
        <h2>Agent Activity</h2>
        <span>{agents.length} active roster entries</span>
      </header>
      <div className="brain-agent-list">
        {agents.map((agent) => (
          <article className="brain-agent" key={agent.name}>
            <strong>{agent.name}</strong>
            <span>{agent.status}</span>
            <small>{agent.current_task}</small>
          </article>
        ))}
      </div>
      <div className="brain-executions">
        {executions.map((execution, index) => (
          <article key={`${execution.agent}-${index}`}>
            <strong>{execution.agent}</strong>
            <span>{execution.task}</span>
            <small>{execution.status} · {execution.duration_ms || 0}ms</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function LogsPanel({ logs }: { logs: BrainLogEntry[] }) {
  const [filter, setFilter] = useState("all");
  const components = useMemo(() => ["all", ...Array.from(new Set(logs.map((log) => log.component))).sort()], [logs]);
  const visibleLogs = filter === "all" ? logs : logs.filter((log) => log.component === filter);

  return (
    <section className="brain-panel brain-log-panel">
      <header>
        <div>
          <h2>Live Logs</h2>
          <span>Backend and launcher streams</span>
        </div>
        <select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter logs by component">
          {components.map((component) => (
            <option key={component} value={component}>
              {component}
            </option>
          ))}
        </select>
      </header>
      <div className="brain-log-stream">
        {visibleLogs.length === 0 ? (
          <p className="empty">No logs for this component.</p>
        ) : (
          visibleLogs.slice(-160).map((log, index) => (
            <pre className={`brain-log ${log.level || "INFO"}`} key={`${log.component}-${log.timestamp}-${index}`}>
              <span>[{log.component}{log.level ? `:${log.level}` : ""}]</span> {log.message}
            </pre>
          ))
        )}
      </div>
    </section>
  );
}

function ArchitecturePanel({ snapshot }: { snapshot: BrainSnapshot }) {
  return (
    <section className="brain-panel brain-architecture">
      <header>
        <h2>Architecture</h2>
        <span>{snapshot.architecture.live_updates}</span>
      </header>
      <div className="brain-module-grid">
        {snapshot.architecture.modules.map((module) => (
          <article className="brain-module" key={module.id}>
            <strong>{module.label}</strong>
            <small>{module.depends_on.length ? `Depends on ${module.depends_on.join(", ")}` : "Root module"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

export function BrainDashboard({ launcher, launcherLogs }: BrainDashboardProps) {
  const [snapshot, setSnapshot] = useState<BrainSnapshot>(emptySnapshot);
  const [backendLogs, setBackendLogs] = useState<BrainLogEntry[]>([]);
  const [connection, setConnection] = useState("connecting");

  useEffect(() => {
    let pollTimer = 0;
    readBrainSnapshot()
      .then((next) => {
        setSnapshot(next);
        setBackendLogs(next.logs || []);
      })
      .catch(() => setConnection("offline"));

    const close = openBrainUpdates(
      (next, logs) => {
        setConnection("live");
        setSnapshot(next);
        setBackendLogs((current) => [...current, ...(logs.length ? logs : next.logs || [])].slice(-300));
      },
      () => {
        setConnection("polling");
        pollTimer = window.setInterval(() => {
          readBrainSnapshot()
            .then((next) => {
              setSnapshot(next);
              setBackendLogs(next.logs || []);
            })
            .catch(() => setConnection("offline"));
        }, 3000);
      }
    );

    return () => {
      close();
      window.clearInterval(pollTimer);
    };
  }, []);

  const launcherLogEntries = useMemo(
    () =>
      launcherLogs.map((log) => ({
        component: log.service,
        level: log.stream,
        message: log.line
      })),
    [launcherLogs]
  );
  const mergedLogs = [...backendLogs, ...launcherLogEntries].slice(-360);

  return (
    <section className="brain-dashboard" aria-label="Anubis Brain Dashboard">
      <header className="brain-header">
        <div>
          <h1>Anubis Brain Dashboard</h1>
          <span>Real-time foundation view · {connection}</span>
        </div>
        <div className="brain-pulse">
          <span className={`brain-led ${connection === "live" ? "ok" : "warn"}`} />
          <strong>{snapshot.timestamp ? formatTime(snapshot.timestamp) : "waiting"}</strong>
        </div>
      </header>
      <div className="brain-grid">
        <HealthPanel snapshot={snapshot} launcher={launcher} />
        <MemoryPanel snapshot={snapshot} />
        <AgentPanel snapshot={snapshot} />
        <CognitiveGraphView snapshot={snapshot} />
        <LogsPanel logs={mergedLogs} />
        <ArchitecturePanel snapshot={snapshot} />
      </div>
    </section>
  );
}
