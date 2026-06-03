import { memo } from "react";
import type { ChatMessage } from "../core/api";

type MessageStreamProps = {
  message: ChatMessage;
  streaming: boolean;
};

export const MessageStream = memo(function MessageStream({ message, streaming }: MessageStreamProps) {
  return (
    <article className={`message ${message.role}`}>
      <div className="message-meta">{messageLabel(message.role)}</div>
      <div className="message-body">
        {renderMessageContent(message.content)}
        {streaming && <span className="stream-cursor" aria-label="Streaming response" />}
      </div>
    </article>
  );
});

function messageLabel(role: ChatMessage["role"]): string {
  if (role === "assistant") {
    return "ANUBIS";
  }

  if (role === "user") {
    return "You";
  }

  return "System";
}

function renderMessageContent(content: string) {
  const blocks = splitCodeFences(content);

  return blocks.map((block, index) => {
    if (block.type === "code") {
      return (
        <pre className="code-block" key={`${block.type}:${index}`}>
          <code>{block.content}</code>
        </pre>
      );
    }

    if (!block.content) {
      return null;
    }

    return <p key={`${block.type}:${index}`}>{block.content}</p>;
  });
}

function splitCodeFences(content: string): Array<{ type: "text" | "code"; content: string }> {
  const parts: Array<{ type: "text" | "code"; content: string }> = [];
  const fencePattern = /```[^\n]*\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = fencePattern.exec(content)) !== null) {
    if (match.index > cursor) {
      parts.push({ type: "text", content: content.slice(cursor, match.index).trimEnd() });
    }

    parts.push({ type: "code", content: match[1].trimEnd() });
    cursor = match.index + match[0].length;
  }

  if (cursor < content.length) {
    parts.push({ type: "text", content: content.slice(cursor).trimEnd() });
  }

  return parts.length ? parts : [{ type: "text", content }];
}
