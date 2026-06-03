import { Send, Square } from "lucide-react";
import { memo } from "react";
import type { FormEvent, KeyboardEvent, RefObject } from "react";

type InputBarProps = {
  value: string;
  loading: boolean;
  inputRef: RefObject<HTMLTextAreaElement>;
  onAbort: () => void;
  onChange: (value: string) => void;
  onSubmit: (event?: FormEvent) => void;
};

export const InputBar = memo(function InputBar({ value, loading, inputRef, onAbort, onChange, onSubmit }: InputBarProps) {
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (loading) {
        return;
      }
      onSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        ref={inputRef}
        value={value}
        disabled={loading}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={loading ? "ANUBIS is responding..." : "Message ANUBIS"}
        rows={1}
      />
      <button
        className={loading ? "stop-button" : ""}
        type={loading ? "button" : "submit"}
        aria-label={loading ? "Stop response" : "Send message"}
        disabled={!loading && !value.trim()}
        onClick={loading ? onAbort : undefined}
      >
        {loading ? <Square size={14} /> : <Send size={17} />}
      </button>
    </form>
  );
});
