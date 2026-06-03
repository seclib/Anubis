import { memo } from "react";
import type { RefObject } from "react";
import type { ChatMessage } from "../core/api";
import { MessageStream } from "./MessageStream";

type ChatProps = {
  messages: ChatMessage[];
  currentStream: string;
  loading: boolean;
  scrollerRef: RefObject<HTMLDivElement>;
};

export const Chat = memo(function Chat({ messages, currentStream, loading, scrollerRef }: ChatProps) {
  const lastMessage = messages[messages.length - 1];
  const streamingMessage = loading && lastMessage?.role === "assistant";

  return (
    <div className="message-list" ref={scrollerRef} aria-label="AI chat conversation">
      {messages.map((message) => (
        <MessageStream
          message={message}
          streaming={loading && message.id === lastMessage?.id && message.role === "assistant"}
          key={message.id}
        />
      ))}
      {loading && !streamingMessage && (
        <article className="message assistant pending">
          <div className="message-meta">ANUBIS</div>
          <div className="message-body">
            <span className="typing-indicator" aria-label="ANUBIS is typing">
              <i />
              <i />
              <i />
            </span>
            {currentStream || "Thinking..."}
          </div>
        </article>
      )}
    </div>
  );
});
