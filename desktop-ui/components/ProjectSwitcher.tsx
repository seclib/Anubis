"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Brain, FileText, MessageCircle, Star, Workflow } from "lucide-react";
import type { Project } from "../lib/types";

export function ProjectSwitcher({
  projects,
  activeProjectId,
  onSelectProject,
}: {
  projects: Project[];
  activeProjectId: string;
  onSelectProject: (projectId: string) => void;
}) {
  const reduceMotion = useReducedMotion();
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? projects[0];

  return (
    <section className="h-full overflow-auto bg-slate-950/40 p-6">
      <div className="pr-14">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">Project memory</p>
        <h2 className="mt-1 text-3xl font-semibold tracking-tight text-slate-50">Projects</h2>
      </div>

      <div className="mt-7 grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-2">
          {projects.map((project) => (
            <motion.button
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
              type="button"
              key={project.id}
              onClick={() => onSelectProject(project.id)}
              className={`w-full rounded-2xl border p-4 text-left transition ${
                activeProjectId === project.id
                  ? "border-cyan-300/35 bg-slate-900"
                  : "border-white/10 bg-slate-900/50 hover:border-white/20"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-800 text-cyan-300">
                  <Workflow size={18} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-slate-50">{project.name}</span>
                    {project.chats.some((chat) => chat.starred) && <Star size={14} className="fill-yellow-300 text-yellow-300" />}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-xs leading-5 text-slate-400">{project.summary}</span>
                </span>
              </div>
            </motion.button>
          ))}
        </aside>

        <motion.div
          key={activeProject.id}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 30 }}
          className="space-y-4"
        >
          <section className="glass-card rounded-2xl p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-50">
              <Brain size={17} />
              Isolated RAG memory
            </div>
            <p className="mt-3 text-sm leading-6 text-slate-300">{activeProject.memory}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {activeProject.tags.map((tag) => (
                <span key={tag} className="rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-cyan-200">
                  {tag}
                </span>
              ))}
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <StatCard icon={MessageCircle} label="Chats" value={activeProject.chats.length} />
            <StatCard icon={FileText} label="Notes" value={activeProject.notes.length} />
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: typeof MessageCircle; label: string; value: number }) {
  return (
    <div className="glass-card rounded-2xl p-5">
      <Icon size={18} className="text-cyan-300" />
      <p className="mt-4 text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-50">{value}</p>
    </div>
  );
}
