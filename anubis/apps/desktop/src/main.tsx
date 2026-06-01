import React, { FormEvent, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, Database, FileText, Search, Send, Settings, Wrench } from "lucide-react";
import { ChatMessage, RagSource, ToolExecutionLog, sendChatMessage } from "./api";
import "./styles.css";

function App() {
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sources, setSources] = useState<RagSource[]>([]);
  const [toolLogs, setToolLogs] = useState<ToolExecutionLog[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const notes = useMemo(() => ["Daily notes", "Project memory", "Research inbox", "Decisions"], []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = input.trim();
    if (!content || isSending) return;
    setInput("");
    const optimistic: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString()
    };
    setMessages((current) => [...current, optimistic]);
    setIsSending(true);
    try {
      const response = await sendChatMessage(content, conversationId);
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, response.message]);
      setSources(response.sources);
      setToolLogs(response.tool_logs);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `AI Core is unavailable: ${error instanceof Error ? error.message : String(error)}`,
          created_at: new Date().toISOString()
        }
      ]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="workspace">
      <aside className="sidebar">
        <div className="brand">
          <Bot size={22} />
          <span>Anubis</span>
        </div>
        <nav className="nav">
          <button className="active" title="Search"><Search size={17} /> Search</button>
          <button title="Notes"><FileText size={17} /> Notes</button>
          <button title="Memory"><Database size={17} /> Memory</button>
          <button title="Tools"><Wrench size={17} /> Tools</button>
        </nav>
        <section className="note-list">
          {notes.map((note) => <button key={note}>{note}</button>)}
        </section>
        <button className="settings" title="Settings"><Settings size={17} /> Settings</button>
      </aside>

      <section className="chat-panel">
        <header className="chat-header">
          <div>
            <h1>AI Workspace</h1>
            <p>Local-first assistant with memory-aware context.</p>
          </div>
          <span className="status">{isSending ? "Thinking" : "Ready"}</span>
        </header>
        <div className="messages">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h2>Ask Anubis anything</h2>
              <p>Your chat, notes, tools, and retrieval context stay organized in one workspace.</p>
            </div>
          ) : (
            messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <span>{message.role}</span>
                <p>{message.content}</p>
              </article>
            ))
          )}
        </div>
        <form className="composer" onSubmit={onSubmit}>
          <input
            aria-label="Message"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask, retrieve, write, or reason..."
          />
          <button disabled={isSending || input.trim().length === 0} title="Send">
            <Send size={18} />
          </button>
        </form>
      </section>

      <aside className="context-panel">
        <section>
          <h2>RAG Sources</h2>
          {sources.length === 0 ? <p className="muted">No sources yet.</p> : sources.map((source) => (
            <article className="source" key={source.chunk_id}>
              <strong>{source.title}</strong>
              <span>{source.score.toFixed(3)}</span>
              <p>{source.excerpt}</p>
            </article>
          ))}
        </section>
        <section>
          <h2>Execution Logs</h2>
          {toolLogs.length === 0 ? <p className="muted">Tool activity will appear here.</p> : toolLogs.map((log) => (
            <article className="log" key={log.id}>
              <strong>{log.tool_name}</strong>
              <span>{log.status}</span>
              <p>{log.summary}</p>
            </article>
          ))}
        </section>
      </aside>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
