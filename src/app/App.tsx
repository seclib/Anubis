import {
  Bot,
  Brain,
  Command,
  Cpu,
  Database,
  Menu,
  PanelRight,
  Send,
  Sparkles,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import "./ui/styles.css";

type Role = "user" | "assistant" | "system";
type ModuleId = "swarm" | "agents" | "memory" | "tools";
type AgentId = "builder" | "researcher" | "analyst";

type Message = {
  id: string;
  role: Role;
  content: string;
  timestamp: string;
};

type AgentState = {
  id: AgentId;
  label: string;
  task: string;
  status: "idle" | "running" | "complete";
  progress: number;
};

type ModuleState = {
  id: ModuleId;
  label: string;
  value: string;
  status: string;
};

const initialAgents: AgentState[] = [
  { id: "builder", label: "Builder", task: "Standing by", status: "idle", progress: 0 },
  { id: "researcher", label: "Researcher", task: "Standing by", status: "idle", progress: 0 },
  { id: "analyst", label: "Analyst", task: "Standing by", status: "idle", progress: 0 },
];

const welcomeMessage: Message = {
  id: "welcome",
  role: "assistant",
  timestamp: "Now",
  content:
    "ANUBIS is online. Send a task, a DSL command, or a swarm goal and I will route it through the operating system.",
};

export default function App() {
  const [messages, setMessages] = useState<Message[]>([welcomeMessage]);
  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(true);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeModule, setActiveModule] = useState<ModuleId>("swarm");
  const [agents, setAgents] = useState<AgentState[]>(initialAgents);
  const [isRunning, setIsRunning] = useState(false);
  const streamRef = useRef<HTMLDivElement | null>(null);

  const modules = useMemo<ModuleState[]>(
    () => [
      {
        id: "swarm",
        label: "Swarm",
        value: isRunning ? "Running" : "Ready",
        status: `${agents.filter((agent) => agent.status === "complete").length}/3 complete`,
      },
      {
        id: "agents",
        label: "Agents",
        value: String(agents.length),
        status: agents.find((agent) => agent.status === "running")?.label ?? "Idle",
      },
      { id: "memory", label: "Memory", value: "Local", status: "Vault connected" },
      { id: "tools", label: "Tools", value: "3", status: "Filesystem, GitHub, Web" },
    ],
    [agents, isRunning],
  );

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setSidebarOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || isRunning) {
      return;
    }

    setInput("");
    pushMessage("user", text);

    if (text.startsWith("/swarm")) {
      runSwarm(text.replace(/^\/swarm\s*/, "") || "build app");
      return;
    }

    if (text.startsWith("/tool")) {
      pushMessage("assistant", toolResponse(text));
      return;
    }

    pushMessage("assistant", standardResponse(text));
  }

  function runSwarm(goal: string) {
    setIsRunning(true);
    setActiveModule("swarm");
    setAgents(planAgents(goal));
    pushMessage("system", `SWARM STARTED\n${goal}`);

    const steps: Array<{ agent: AgentId; progress: number; status?: AgentState["status"] }> = [
      { agent: "builder", progress: 35, status: "running" },
      { agent: "researcher", progress: 45, status: "running" },
      { agent: "analyst", progress: 30, status: "running" },
      { agent: "builder", progress: 72 },
      { agent: "researcher", progress: 82 },
      { agent: "analyst", progress: 64 },
      { agent: "builder", progress: 100, status: "complete" },
      { agent: "researcher", progress: 100, status: "complete" },
      { agent: "analyst", progress: 100, status: "complete" },
    ];

    steps.forEach((step, index) => {
      window.setTimeout(() => {
        setAgents((current) =>
          current.map((agent) =>
            agent.id === step.agent
              ? { ...agent, progress: step.progress, status: step.status ?? agent.status }
              : agent,
          ),
        );
      }, 180 + index * 180);
    });

    window.setTimeout(() => {
      pushMessage("assistant", swarmResponse(goal));
      setIsRunning(false);
    }, 1900);
  }

  function pushMessage(role: Role, content: string) {
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role,
        content,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function runPaletteCommand(command: string) {
    setPaletteOpen(false);
    setInput(command);
    if (command.startsWith("/swarm")) {
      pushMessage("user", command);
      runSwarm(command.replace(/^\/swarm\s*/, ""));
      setInput("");
    }
  }

  return (
    <main className="anubis-os">
      <aside className={`module-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">
            <Sparkles size={18} />
          </div>
          <div>
            <strong>ANUBIS</strong>
            <span>AI Operating System</span>
          </div>
        </div>

        <nav className="module-list" aria-label="ANUBIS modules">
          {modules.map((module) => (
            <button
              className={`module-item ${activeModule === module.id ? "active" : ""}`}
              key={module.id}
              onClick={() => {
                setActiveModule(module.id);
                setSidebarOpen(false);
              }}
            >
              <ModuleIcon id={module.id} />
              <span>
                <strong>{module.label}</strong>
                <small>{module.status}</small>
              </span>
              <em>{module.value}</em>
            </button>
          ))}
        </nav>
      </aside>

      <section className="chat-shell">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} aria-label="Open modules">
            <Menu size={20} />
          </button>
          <div className="session-title">
            <Bot size={18} />
            <span>Operating Session</span>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
              <Command size={19} />
            </button>
            <button className="icon-button" onClick={() => setContextOpen((current) => !current)} aria-label="Toggle context">
              <PanelRight size={19} />
            </button>
          </div>
        </header>

        <div className="message-stream" ref={streamRef}>
          {messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <div className="message-meta">
                <span>{message.role === "assistant" ? "ANUBIS" : message.role === "system" ? "System" : "You"}</span>
                <time>{message.timestamp}</time>
              </div>
              <pre>{message.content}</pre>
            </article>
          ))}
        </div>

        <form className="composer" onSubmit={submit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="/swarm build landing page"
            rows={1}
          />
          <button className="send-button" type="submit" disabled={!input.trim() || isRunning} aria-label="Send">
            <Send size={18} />
          </button>
        </form>
      </section>

      {contextOpen && (
        <aside className="context-panel">
          <div className="panel-header">
            <span>{modules.find((module) => module.id === activeModule)?.label}</span>
          </div>
          {activeModule === "swarm" && <SwarmLive agents={agents} />}
          {activeModule === "agents" && <AgentList agents={agents} />}
          {activeModule === "memory" && <MemoryView />}
          {activeModule === "tools" && <ToolsView />}
        </aside>
      )}

      {paletteOpen && (
        <div className="palette-backdrop" onMouseDown={() => setPaletteOpen(false)}>
          <section className="command-palette" onMouseDown={(event) => event.stopPropagation()}>
            <div className="palette-input">
              <Command size={18} />
              <input autoFocus placeholder="Run command" onKeyDown={(event) => {
                if (event.key === "Enter") {
                  runPaletteCommand(event.currentTarget.value);
                }
              }} />
            </div>
            {["/swarm build app", "/agent builder: create UI", "/tool web search AI agents", "/analyze repo"].map((command) => (
              <button key={command} onClick={() => runPaletteCommand(command)}>
                <span>{command}</span>
              </button>
            ))}
          </section>
        </div>
      )}

      {sidebarOpen && <button className="scrim" onClick={() => setSidebarOpen(false)} aria-label="Close modules" />}
    </main>
  );
}

function ModuleIcon({ id }: { id: ModuleId }) {
  if (id === "swarm") return <Zap size={18} />;
  if (id === "agents") return <Cpu size={18} />;
  if (id === "memory") return <Database size={18} />;
  return <Wrench size={18} />;
}

function SwarmLive({ agents }: { agents: AgentState[] }) {
  return (
    <div className="swarm-live">
      {agents.map((agent) => (
        <div className="agent-meter" key={agent.id}>
          <div>
            <strong>{agent.label}</strong>
            <span>{agent.task}</span>
          </div>
          <Progress value={agent.progress} />
        </div>
      ))}
    </div>
  );
}

function AgentList({ agents }: { agents: AgentState[] }) {
  return (
    <div className="panel-list">
      {agents.map((agent) => (
        <div className="panel-row" key={agent.id}>
          <span>{agent.label}</span>
          <em>{agent.status}</em>
        </div>
      ))}
    </div>
  );
}

function MemoryView() {
  return (
    <div className="panel-list">
      <div className="panel-row"><span>Vault</span><em>connected</em></div>
      <div className="panel-row"><span>RAG</span><em>ready</em></div>
      <div className="panel-row"><span>Session</span><em>active</em></div>
    </div>
  );
}

function ToolsView() {
  return (
    <div className="panel-list">
      <div className="panel-row"><span>Filesystem</span><em>local</em></div>
      <div className="panel-row"><span>GitHub</span><em>mock</em></div>
      <div className="panel-row"><span>Web</span><em>mock</em></div>
    </div>
  );
}

function Progress({ value }: { value: number }) {
  return (
    <div className="progress">
      <div style={{ width: `${value}%` }} />
      <span>{value}%</span>
    </div>
  );
}

function planAgents(goal: string): AgentState[] {
  const clean = goal.trim() || "build app";
  return [
    { id: "builder", label: "Builder", task: `Structure for ${clean}`, status: "running", progress: 8 },
    { id: "researcher", label: "Researcher", task: `Context for ${clean}`, status: "running", progress: 8 },
    { id: "analyst", label: "Analyst", task: `Review for ${clean}`, status: "running", progress: 8 },
  ];
}

function swarmResponse(goal: string) {
  const clean = goal.trim() || "build app";
  return [
    "TASK:",
    clean,
    "",
    "STATUS:",
    "planning complete",
    "parallel execution complete",
    "aggregation complete",
    "",
    "RESULT:",
    `Builder created the working structure for ${clean}. Researcher gathered context and constraints. Analyst refined the execution path and reduced risk.`,
    "",
    "BREAKDOWN:",
    `- builder contribution: structure for ${clean}`,
    `- researcher contribution: context for ${clean}`,
    `- analyst contribution: optimization for ${clean}`,
    "",
    "FINAL INSIGHT:",
    "The swarm produced one execution-ready direction from structure, context, and review.",
  ].join("\n");
}

function toolResponse(command: string) {
  return ["TASK:", command, "", "STATUS:", "tool routed", "", "RESULT:", "Tool request accepted by the ANUBIS OS router."].join("\n");
}

function standardResponse(text: string) {
  return ["TASK:", text, "", "STATUS:", "ready", "", "RESULT:", "I can route this through chat, DSL, tools, agents, or swarm execution."].join("\n");
}
