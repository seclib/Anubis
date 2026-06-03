"use client";

import { AnimatePresence, motion } from "framer-motion";
import { FileText, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { projects as initialProjects } from "../lib/data";
import { overlayVariants, panelVariants } from "../lib/motion";
import type { Project, View } from "../lib/types";
import { BottomSheetModal } from "./BottomSheetModal";
import { ChatWindow } from "./ChatWindow";
import { CommandPalette } from "./CommandPalette";
import { NotesExplorer } from "./NotesExplorer";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { SidebarDrawer } from "./SidebarDrawer";

export function AppShell() {
  const [projects] = useState<Project[]>(initialProjects);
  const [activeProjectId, setActiveProjectId] = useState(projects[0].id);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeView, setActiveView] = useState<View | null>(null);

  const activeProject = projects.find((project) => project.id === activeProjectId) ?? projects[0];
  const panelOpen = activeView !== null;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isCommandK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isCommandK) {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setDrawerOpen(false);
        setActiveView(null);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function selectView(view: View) {
    setDrawerOpen(false);
    if (view === "settings" || view === "files") {
      setActiveView(view);
      return;
    }
    setActiveView(view);
  }

  return (
    <main className="relative h-screen overflow-hidden bg-[radial-gradient(circle_at_top,rgba(124,58,237,.14),transparent_34%),#0b0f17] text-slate-50">
      <ChatWindow
        project={activeProject}
        drawerOpen={drawerOpen}
        panelOpen={panelOpen}
        onOpenSidebar={() => setDrawerOpen(true)}
        onOpenContext={() => setActiveView("projects")}
      />

      <SidebarDrawer
        open={drawerOpen}
        activeView={activeView}
        onClose={() => setDrawerOpen(false)}
        onSelect={selectView}
        onNewChat={() => {
          setActiveView(null);
          setDrawerOpen(false);
        }}
      />

      <CommandPalette
        open={paletteOpen}
        projects={projects}
        onClose={() => setPaletteOpen(false)}
        onSelectView={(view) => {
          setActiveView(view);
          setDrawerOpen(false);
        }}
        onSelectProject={(projectId) => {
          setActiveProjectId(projectId);
          setActiveView(null);
        }}
      />

      <AnimatePresence>
        {activeView && !["settings", "files"].includes(activeView) && (
          <motion.div
            variants={overlayVariants}
            initial="closed"
            animate="open"
            exit="closed"
            className="fixed inset-0 z-20 flex justify-end bg-slate-950/30"
          >
            <button type="button" className="absolute inset-0" onClick={() => setActiveView(null)} aria-label="Close panel" />
            <motion.section
              variants={panelVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              drag="x"
              dragConstraints={{ left: 0, right: 0 }}
              dragElastic={0.14}
              onDragEnd={(_, info) => {
                if (info.offset.x > 90 || info.velocity.x > 600) setActiveView(null);
              }}
              className={`glass relative z-10 h-full overflow-hidden rounded-l-[24px] ${
                activeView === "projects" ? "w-[min(1120px,calc(100vw-96px))]" : "w-[min(620px,calc(100vw-96px))]"
              }`}
            >
              {activeView === "projects" && (
                <ProjectSwitcher projects={projects} activeProjectId={activeProjectId} onSelectProject={setActiveProjectId} />
              )}
              {activeView === "notes" && <NotesExplorer project={activeProject} />}
              {activeView === "chats" && <ChatsPanel project={activeProject} />}
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>

      <BottomSheetModal open={activeView === "files"} title="Files" onClose={() => setActiveView(null)}>
        <div className="space-y-2">
          {activeProject.files.map((file) => (
            <div key={file.id} className="flex items-center gap-3 rounded-2xl bg-slate-950/35 px-4 py-3">
              <FileText size={18} className="text-cyan-300" />
              <div>
                <p className="text-sm font-medium text-slate-50">{file.name}</p>
                <p className="text-xs text-slate-400">
                  {file.kind} · {file.size}
                </p>
              </div>
            </div>
          ))}
        </div>
      </BottomSheetModal>

      <BottomSheetModal open={activeView === "settings"} title="Settings" onClose={() => setActiveView(null)}>
        <div className="space-y-3">
          {["Dark mode", "Silent autosave", "Project-isolated memory"].map((label) => (
            <div key={label} className="flex items-center justify-between rounded-2xl bg-slate-950/35 px-4 py-3">
              <span className="text-sm text-slate-200">{label}</span>
              <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-medium text-cyan-200">On</span>
            </div>
          ))}
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Settings size={14} />
            Settings are autosaved silently.
          </div>
        </div>
      </BottomSheetModal>
    </main>
  );
}

function ChatsPanel({ project }: { project: Project }) {
  return (
    <section className="h-full overflow-auto bg-slate-950/35 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">Conversation history</p>
      <h2 className="mt-1 text-3xl font-semibold text-slate-50">Chats</h2>
      <div className="mt-7 space-y-2">
        {project.chats.map((chat) => (
          <div key={chat.id} className="glass-card rounded-2xl p-4">
            <p className="text-sm font-semibold text-slate-50">{chat.title}</p>
            <p className="mt-1 text-xs text-slate-400">{chat.updatedAt}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
