import { Loader2, Send } from "lucide-react";
import type { FormEvent, KeyboardEvent, RefObject } from "react";

type InputBarProps = {
  value: string;
  busy: boolean;
  inputRef: RefObject<HTMLTextAreaElement>;
  onChange: (value: string) => void;
  onSubmit: (event?: FormEvent) => void;
};

export function InputBar({ value, busy, inputRef, onChange, onSubmit }: InputBarProps) {
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        ref={inputRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask ANUBIS"
        rows={1}
      />
      <button type="submit" aria-label="Send message" disabled={busy || !value.trim()}>
        {busy ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
      </button>
    </form>
  );
}
