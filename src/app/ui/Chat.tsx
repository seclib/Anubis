import type { RefObject } from "react";
import type { ChatMessage } from "../core/api";

type ChatProps = {
  messages: ChatMessage[];
  busy: boolean;
  scrollerRef: RefObject<HTMLDivElement>;
};

export function Chat({ messages, busy, scrollerRef }: ChatProps) {
  const lastMessage = messages[messages.length - 1];
  const streamingMessage = busy && lastMessage?.role === "assistant";

  return (
    <div className="message-list" ref={scrollerRef} aria-label="AI chat conversation">
      {messages.map((message) => (
        <article className={`message ${message.role}`} key={message.id}>
          <div className="message-meta">{message.role === "assistant" ? "ANUBIS" : message.role === "user" ? "You" : "System"}</div>
          <p>
            {message.content}
            {busy && message.id === lastMessage?.id && message.role === "assistant" && (
              <span className="stream-cursor" />
            )}
          </p>
        </article>
      ))}
      {busy && !streamingMessage && (
        <article className="message assistant pending">
          <div className="message-meta">ANUBIS</div>
          <p>
            <span className="stream-cursor" />
            Thinking through the local runtime...
          </p>
        </article>
      )}
    </div>
  );
}
