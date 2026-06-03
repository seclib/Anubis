"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Paperclip, Send, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { AssistantMode } from "../lib/types";

const modes: Array<{ id: AssistantMode; label: string }> = [
  { id: "short", label: "Short" },
  { id: "deep", label: "Deep analysis" },
  { id: "builder", label: "Builder" },
];

export function InputBar({
  value,
  mode,
  loading,
  toolsVisible,
  onChange,
  onModeChange,
  onSubmit,
}: {
  value: string;
  mode: AssistantMode;
  loading: boolean;
  toolsVisible: boolean;
  onChange: (value: string) => void;
  onModeChange: (mode: AssistantMode) => void;
  onSubmit: () => void;
}) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [focused, setFocused] = useState(false);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "44px";
    input.style.height = `${Math.min(input.scrollHeight, 144)}px`;
  }, [value]);

  return (
    <div className="border-t border-white/10 bg-slate-950/20 p-4">
      <div className="hide-scrollbar mb-3 flex gap-2 overflow-x-auto">
        {modes.map((item) => (
          <motion.button
            whileTap={reduceMotion ? undefined : { scale: 0.94 }}
            type="button"
            key={item.id}
            onClick={() => onModeChange(item.id)}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${
              mode === item.id ? "bg-violet-600 text-white" : "bg-slate-900/80 text-slate-400 hover:text-white"
            }`}
          >
            {item.label}
          </motion.button>
        ))}
      </div>
      <motion.form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
        animate={{
          scale: loading ? 0.988 : 1,
          boxShadow: focused
            ? "0 0 0 1px rgba(34,211,238,.22), 0 0 42px rgba(34,211,238,.10), 0 18px 58px rgba(0,0,0,.28)"
            : "0 14px 48px rgba(0,0,0,.24)",
        }}
        transition={{ type: "spring", stiffness: 360, damping: 34 }}
        className="flex items-end gap-2 rounded-2xl border border-white/10 bg-slate-900/80 p-2 backdrop-blur-2xl"
      >
        <motion.button
          whileTap={reduceMotion ? undefined : { scale: 0.9 }}
          type="button"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-950/60 text-slate-400 hover:text-white"
          aria-label="Attach files"
        >
          <Paperclip size={18} />
        </motion.button>
        <textarea
          ref={inputRef}
          value={value}
          disabled={loading}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSubmit();
            }
          }}
          rows={1}
          className="max-h-36 min-h-11 min-w-0 flex-1 resize-none bg-transparent px-2 py-3 text-[15px] leading-6 text-slate-50 outline-none placeholder:text-slate-500"
          placeholder={loading ? "ANUBIS is thinking..." : "Message ANUBIS"}
        />
        {toolsVisible && (
          <button type="button" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-950/60 text-slate-400">
            <SlidersHorizontal size={18} />
          </button>
        )}
        <motion.button
          whileTap={reduceMotion ? undefined : { scale: 0.88 }}
          type="submit"
          disabled={!value.trim() || loading}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-violet-600 text-white disabled:cursor-not-allowed disabled:bg-slate-700"
          aria-label="Send"
        >
          <Send size={18} />
        </motion.button>
      </motion.form>
    </div>
  );
}
