"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Bot, Brain, Menu, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { initialMessages } from "../lib/data";
import { softSpring } from "../lib/motion";
import type { AssistantMode, ChatMessage, Project } from "../lib/types";
import { InputBar } from "./InputBar";
import { MessageBubble } from "./MessageBubble";

export function ChatWindow({
  project,
  drawerOpen,
  panelOpen,
  onOpenSidebar,
  onOpenContext,
}: {
  project: Project;
  drawerOpen: boolean;
  panelOpen: boolean;
  onOpenSidebar: () => void;
  onOpenContext: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<AssistantMode>("deep");
  const [loading, setLoading] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    setMessages(initialMessages);
    setInput("");
    setLoading(false);
    stickToBottomRef.current = true;
  }, [project.id]);

  useEffect(() => {
    if (!stickToBottomRef.current || !scrollerRef.current) return;
    scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages, loading]);

  function onScroll() {
    const element = scrollerRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    stickToBottomRef.current = distance < 90;
  }

  function toggleStar(messageId: string) {
    setMessages((current) =>
      current.map((message) => (message.id === messageId ? { ...message, starred: !message.starred } : message)),
    );
  }

  async function sendMessage(prompt = input.trim()) {
    if (!prompt || loading) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: prompt,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setLoading(true);

    await new Promise((resolve) => window.setTimeout(resolve, 420));

    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: responseFor(prompt, project, mode),
    };
    setMessages((current) => [...current, assistantMessage]);
    setLoading(false);
  }

  return (
    <motion.section
      animate={{
        scale: drawerOpen || panelOpen ? 0.985 : 1,
        y: drawerOpen || panelOpen ? 5 : 0,
        filter: drawerOpen || panelOpen ? "brightness(.82) saturate(.9)" : "brightness(1) saturate(1)",
      }}
      transition={reduceMotion ? { duration: 0 } : softSpring}
      className="flex h-full min-h-0 w-full items-center justify-center px-6 py-6"
    >
      <motion.div
        layout
        className="glass flex h-full max-h-[940px] w-full max-w-[700px] flex-col overflow-hidden rounded-[20px]"
      >
        <header className="flex items-center justify-between border-b border-white/10 px-5 py-4">
          <div className="flex items-center gap-3">
            <motion.button
              whileTap={reduceMotion ? undefined : { scale: 0.92 }}
              type="button"
              onClick={onOpenSidebar}
              className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-800/80 text-slate-200"
              aria-label="Open menu"
            >
              <Menu size={20} />
            </motion.button>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-slate-50">ANUBIS</h1>
              <p className="text-xs text-slate-400">{project.name}</p>
            </div>
          </div>
          <motion.button
            whileTap={reduceMotion ? undefined : { scale: 0.92 }}
            type="button"
            onClick={onOpenContext}
            className="flex h-11 w-11 items-center justify-center rounded-2xl bg-violet-600 text-white"
            aria-label="Open project context"
          >
            <Bot size={19} />
          </motion.button>
        </header>

        <div ref={scrollerRef} onScroll={onScroll} className="momentum min-h-0 flex-1 space-y-4 overflow-auto px-5 py-5">
          <div className="mx-auto flex w-fit items-center gap-2 rounded-full bg-cyan-400/10 px-3 py-1 text-xs text-cyan-300">
            <Sparkles size={13} />
            Isolated context: {project.name}
          </div>

          <motion.section
            initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={softSpring}
            className="glass-card rounded-2xl p-4"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-cyan-300">
                <Brain size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-50">Workspace memory</p>
                <p className="mt-1 text-sm leading-6 text-slate-300">{project.summary}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {project.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-cyan-200">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </motion.section>

          <div className="hide-scrollbar momentum flex gap-2 overflow-x-auto">
            {suggestionsFor(project).map((suggestion) => (
              <motion.button
                whileTap={reduceMotion ? undefined : { scale: 0.96 }}
                type="button"
                key={suggestion}
                onClick={() => sendMessage(suggestion)}
                className="shrink-0 rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-2 text-left text-xs leading-5 text-slate-300 hover:border-cyan-300/40"
              >
                {suggestion}
              </motion.button>
            ))}
          </div>

          <AnimatePresence initial={false}>
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} onStar={toggleStar} />
            ))}
          </AnimatePresence>

          {loading && <TypingIndicator />}
        </div>

        <InputBar
          value={input}
          mode={mode}
          loading={loading}
          toolsVisible={false}
          onChange={setInput}
          onModeChange={setMode}
          onSubmit={() => sendMessage()}
        />
      </motion.div>
    </motion.section>
  );
}

function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, filter: "blur(3px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      exit={{ opacity: 0, y: 4 }}
      className="mr-auto flex max-w-[88%] items-center gap-2 rounded-2xl rounded-bl-md bg-slate-900/80 px-4 py-3"
    >
      {[0, 1, 2].map((item) => (
        <motion.span
          key={item}
          animate={{ opacity: [0.35, 1, 0.35], x: [0, 1, 0], scale: [0.82, 1, 0.82] }}
          transition={{ duration: 1.3, repeat: Infinity, delay: item * 0.14 }}
          className="h-2 w-2 rounded-full bg-cyan-300"
        />
      ))}
    </motion.div>
  );
}

function suggestionsFor(project: Project): string[] {
  if (project.tags.includes("pentest")) {
    return ["Summarize the scope", "List open hypotheses", "Turn notes into a research plan"];
  }
  if (project.tags.includes("dev")) {
    return ["Suggest the next product iteration", "Summarize key architecture decisions", "Identify UX risks"];
  }
  return ["Summarize this workspace", "Extract important insights", "Organize this project"];
}

function responseFor(prompt: string, project: Project, mode: AssistantMode) {
  if (mode === "short") {
    return `## Short answer\n\n${project.summary}`;
  }
  if (mode === "builder") {
    return `## Builder mode\n\n- Project: ${project.name}\n- Memory scope: isolated\n- Tags: ${project.tags.join(", ")}\n\nNext, I would convert this into a compact implementation plan.`;
  }
  if (prompt.toLowerCase().includes("summar")) {
    return `## Project summary\n\n${project.summary}\n\n- Chats: ${project.chats.length}\n- Notes: ${project.notes.length}\n- Files: ${project.files.length}`;
  }
  return `## Deep analysis\n\nI will stay inside **${project.name}** and use only its project memory.\n\n- ${project.memory}\n- Relevant tags: ${project.tags.join(", ")}\n- Best next step: clarify the decision you want to make.`;
}
