"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { BookOpen, FileText, Search, Workflow } from "lucide-react";
import { paletteVariants, staggerList } from "../lib/motion";
import type { Project, View } from "../lib/types";

export function CommandPalette({
  open,
  projects,
  onClose,
  onSelectView,
  onSelectProject,
}: {
  open: boolean;
  projects: Project[];
  onClose: () => void;
  onSelectView: (view: View) => void;
  onSelectProject: (projectId: string) => void;
}) {
  const reduceMotion = useReducedMotion();
  const results = [
    { id: "projects", label: "Open Projects", icon: Workflow, action: () => onSelectView("projects") },
    { id: "notes", label: "Search Notes", icon: BookOpen, action: () => onSelectView("notes") },
    { id: "files", label: "Browse Files", icon: FileText, action: () => onSelectView("files") },
    ...projects.map((project) => ({
      id: project.id,
      label: project.name,
      icon: Workflow,
      action: () => onSelectProject(project.id),
    })),
  ];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
          animate={{ opacity: 1, backdropFilter: "blur(18px)" }}
          exit={{ opacity: 0, backdropFilter: "blur(0px)" }}
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 pt-[14vh]"
          onMouseDown={onClose}
        >
          <motion.section
            variants={reduceMotion ? undefined : paletteVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            onMouseDown={(event) => event.stopPropagation()}
            className="glass w-[min(680px,calc(100vw-32px))] rounded-[20px] p-3"
          >
            <div className="flex h-14 items-center gap-3 rounded-2xl bg-slate-950/45 px-4">
              <Search size={19} className="text-cyan-300" />
              <input
                autoFocus
                placeholder="Search ANUBIS..."
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-50 outline-none placeholder:text-slate-500"
              />
            </div>
            <motion.div variants={staggerList} animate="animate" className="mt-3 space-y-1">
              {results.map((result) => {
                const Icon = result.icon;
                return (
                  <motion.button
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    type="button"
                    key={result.id}
                    onClick={() => {
                      result.action();
                      onClose();
                    }}
                    className="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm text-slate-300 hover:bg-slate-800/70 hover:text-white"
                  >
                    <Icon size={18} />
                    {result.label}
                  </motion.button>
                );
              })}
            </motion.div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
