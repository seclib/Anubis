import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { chat, listNotes, NoteSummary, RagChunk, readNote, writeNote } from "./api";
import "./styles.css";

function App() {
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [activePath, setActivePath] = useState("");
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [message, setMessage] = useState("");
  const [answer, setAnswer] = useState("");
  const [chunks, setChunks] = useState<RagChunk[]>([]);
  const [status, setStatus] = useState("Ready");
  const [selectedText, setSelectedText] = useState("");
  const dirty = content !== savedContent;

  useEffect(() => {
    listNotes().then(setNotes).catch(() => setNotes([]));
  }, []);

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
    <main className="shell">
      <aside className="vault-pane">
        <header className="pane-header">
          <div>
            <h1>Anubis</h1>
            <span>Markdown Vault</span>
          </div>
          <button className="icon-button" onClick={() => listNotes().then(setNotes)}>
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
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
