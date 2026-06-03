import { Brain, ChevronDown, Command, ShieldCheck, Terminal } from "lucide-react";
import { FormEvent, memo, RefObject, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../core/api";
import { Chat } from "./Chat";
import { InputBar } from "./InputBar";

type ChatViewProps = {
  messages: ChatMessage[];
  currentStream: string;
  loading: boolean;
  value: string;
  inputRef: RefObject<HTMLTextAreaElement>;
  onAbort: () => void;
  onChange: (value: string) => void;
  onSubmit: (event?: FormEvent) => void;
};

export const ChatView = memo(function ChatView({
  messages,
  currentStream,
  loading,
  value,
  inputRef,
  onAbort,
  onChange,
  onSubmit,
}: ChatViewProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [thinkingOpen, setThinkingOpen] = useState(true);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      scroller.scrollTop = scroller.scrollHeight;
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [messages, currentStream, loading]);

  return (
    <>
      <header className="phone-header">
        <div className="anubis-lockup">
          <span className="anubis-logo" aria-hidden="true">
            <ShieldCheck size={18} />
          </span>
          <div>
            <span>ANUBIS OS</span>
            <strong>{loading ? "THINKING" : "ONLINE"}</strong>
          </div>
        </div>
        <div className="header-actions">
          <Command size={16} />
          <Terminal size={16} />
        </div>
      </header>

      <Chat
        messages={messages}
        currentStream={currentStream}
        loading={loading}
        scrollerRef={scrollerRef}
      />
      <section className={`thinking-panel ${thinkingOpen ? "open" : ""}`} aria-label="Agent thinking process">
        <button type="button" onClick={() => setThinkingOpen((value) => !value)}>
          <span>
            <Brain size={15} />
            Agent loop
          </span>
          <ChevronDown size={16} />
        </button>
        <div className="thinking-steps">
          <span className="complete">Context retrieved</span>
          <span className={loading ? "active" : "complete"}>{loading ? "Streaming response" : "Response stable"}</span>
          <span>Tool routing armed</span>
        </div>
      </section>
      <InputBar
        value={value}
        loading={loading}
        inputRef={inputRef}
        onAbort={onAbort}
        onChange={onChange}
        onSubmit={onSubmit}
      />
    </>
  );
});
