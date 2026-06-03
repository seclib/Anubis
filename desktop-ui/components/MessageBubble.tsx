"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Star } from "lucide-react";
import { messageVariants } from "../lib/motion";
import type { ChatMessage } from "../lib/types";

export function MessageBubble({
  message,
  onStar,
}: {
  message: ChatMessage;
  onStar: (messageId: string) => void;
}) {
  const reduceMotion = useReducedMotion();
  const isUser = message.role === "user";

  return (
    <motion.article
      layout
      variants={reduceMotion ? undefined : messageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className={`group flex max-w-[88%] items-start gap-2 ${isUser ? "ml-auto flex-row-reverse" : "mr-auto"}`}
    >
      <div
        className={`rounded-2xl px-4 py-3 text-[15px] leading-7 ${
          isUser
            ? "rounded-br-md bg-violet-600 text-slate-50 shadow-[0_12px_40px_rgba(124,58,237,0.22)]"
            : "rounded-bl-md glass-card text-slate-100"
        }`}
      >
        <RichText content={message.content} />
      </div>
      <motion.button
        whileTap={reduceMotion ? undefined : { scale: 0.92 }}
        type="button"
        onClick={() => onStar(message.id)}
        className={`mt-1 flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-slate-950/40 text-slate-400 opacity-0 shadow-lg backdrop-blur-xl transition group-hover:opacity-100 ${
          message.starred ? "opacity-100 text-yellow-300" : ""
        }`}
        aria-label="Star message"
      >
        <Star size={15} className={message.starred ? "fill-yellow-300" : ""} />
      </motion.button>
    </motion.article>
  );
}

function RichText({ content }: { content: string }) {
  return (
    <div className="space-y-2">
      {content.split("\n").map((line, index) => {
        const value = line.trim();
        if (!value) return null;
        if (value.startsWith("## ")) {
          return (
            <motion.h3
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, delay: Math.min(index * 0.035, 0.2) }}
              className="text-base font-semibold text-slate-50"
              key={`${value}-${index}`}
            >
              {value.replace(/^##\s*/, "")}
            </motion.h3>
          );
        }
        if (value.startsWith("- ")) {
          return (
            <motion.p
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, delay: Math.min(index * 0.035, 0.2) }}
              className="pl-2 text-slate-200"
              key={`${value}-${index}`}
            >
              <span className="mr-2 text-cyan-300">•</span>
              {value.replace(/^-\s*/, "")}
            </motion.p>
          );
        }
        if (value.startsWith("```")) return null;
        return (
          <motion.p
            initial={{ opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.16, delay: Math.min(index * 0.035, 0.2) }}
            className="text-slate-200"
            key={`${value}-${index}`}
          >
            {value}
          </motion.p>
        );
      })}
    </div>
  );
}
