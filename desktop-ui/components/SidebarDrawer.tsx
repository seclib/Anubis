"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { BookOpen, FileText, MessageCircle, Plus, Settings, ShieldCheck, Workflow, X } from "lucide-react";
import { drawerVariants, overlayVariants } from "../lib/motion";
import type { View } from "../lib/types";

const items: Array<{ id: View; label: string; icon: typeof MessageCircle }> = [
  { id: "chats", label: "Chats", icon: MessageCircle },
  { id: "projects", label: "Projects", icon: Workflow },
  { id: "notes", label: "Notes", icon: BookOpen },
  { id: "files", label: "Files", icon: FileText },
  { id: "settings", label: "Settings", icon: Settings },
];

export function SidebarDrawer({
  open,
  activeView,
  onClose,
  onSelect,
  onNewChat,
}: {
  open: boolean;
  activeView: View | null;
  onClose: () => void;
  onSelect: (view: View) => void;
  onNewChat: () => void;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button
            type="button"
            variants={reduceMotion ? undefined : overlayVariants}
            initial="closed"
            animate="open"
            exit="closed"
            onClick={onClose}
            className="fixed inset-0 z-30 bg-slate-950/35 backdrop-blur-xl"
            aria-label="Close navigation"
          />
          <motion.aside
            variants={reduceMotion ? undefined : drawerVariants}
            initial="closed"
            animate="open"
            exit="closed"
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.16}
            onDragEnd={(_, info) => {
              if (info.offset.x < -80 || info.velocity.x < -500) onClose();
            }}
            className="glass fixed left-4 top-4 z-40 flex h-[calc(100vh-32px)] w-[300px] flex-col rounded-[20px] px-4 py-5"
          >
            <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-white/10" />
            <button
              type="button"
              onClick={onClose}
              className="absolute -right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-slate-900/90 text-slate-300"
              aria-label="Close"
            >
              <X size={16} />
            </button>
            <div className="flex items-center gap-3 px-1">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-600 text-white">
                <ShieldCheck size={22} />
              </span>
              <div>
                <h2 className="font-semibold text-slate-50">ANUBIS</h2>
                <p className="text-xs text-slate-400">AI cognition OS</p>
              </div>
            </div>
            <motion.button
              whileTap={reduceMotion ? undefined : { scale: 0.96 }}
              type="button"
              onClick={onNewChat}
              className="mt-6 flex h-12 items-center gap-3 rounded-2xl bg-violet-600 px-4 text-sm font-semibold text-white"
            >
              <Plus size={18} />
              New chat
            </motion.button>
            <nav className="mt-6 flex flex-1 flex-col gap-2">
              {items.map((item) => {
                const Icon = item.icon;
                const active = activeView === item.id;
                return (
                  <motion.button
                    whileTap={reduceMotion ? undefined : { scale: 0.98 }}
                    type="button"
                    key={item.id}
                    onClick={() => onSelect(item.id)}
                    className={`flex h-11 items-center gap-3 rounded-2xl px-3 text-sm transition ${
                      active ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/70 hover:text-white"
                    }`}
                  >
                    <Icon size={19} />
                    {item.label}
                  </motion.button>
                );
              })}
            </nav>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
