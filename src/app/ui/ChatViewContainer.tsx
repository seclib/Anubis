import { memo, useCallback, useRef } from "react";
import { useAnubisStore } from "../state/anubisStore";
import { ChatView } from "./ChatView";

export const ChatViewContainer = memo(function ChatViewContainer() {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortAgent = useAnubisStore((state) => state.abortAgent);
  const currentStream = useAnubisStore((state) => state.currentStream);
  const input = useAnubisStore((state) => state.input);
  const loading = useAnubisStore((state) => state.loading);
  const messages = useAnubisStore((state) => state.messages);
  const runAgent = useAnubisStore((state) => state.runAgent);
  const setInput = useAnubisStore((state) => state.setInput);

  const submitPrompt = useCallback(async (event?: React.FormEvent) => {
    event?.preventDefault();
    await runAgent(input);
    inputRef.current?.focus();
  }, [input, runAgent]);

  return (
    <ChatView
      messages={messages}
      currentStream={currentStream}
      loading={loading}
      value={input}
      inputRef={inputRef}
      onAbort={abortAgent}
      onChange={setInput}
      onSubmit={submitPrompt}
    />
  );
});
