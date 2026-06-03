"use client";

import { motion } from "framer-motion";
import { BookOpen, Link2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import type { Note, Project } from "../lib/types";

export function NotesExplorer({ project }: { project: Project }) {
  const [query, setQuery] = useState("");
  const notes = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return project.notes;
    return project.notes.filter((note) => `${note.title} ${note.body}`.toLowerCase().includes(normalized));
  }, [project.notes, query]);

  return (
    <section className="h-full overflow-auto bg-slate-950/40 p-6">
      <div className="pr-14">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">RAG knowledge base</p>
        <h2 className="mt-1 text-3xl font-semibold tracking-tight text-slate-50">Notes</h2>
      </div>
      <label className="mt-7 flex h-13 items-center gap-3 rounded-2xl border border-white/10 bg-slate-900/70 px-4">
        <Search size={18} className="text-slate-400" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search notes and linked references..."
          className="min-w-0 flex-1 bg-transparent text-sm text-slate-50 outline-none placeholder:text-slate-500"
        />
      </label>
      <div className="mt-5 space-y-3">
        {notes.map((note, index) => (
          <NoteCard note={note} index={index} key={note.id} />
        ))}
      </div>
    </section>
  );
}

function NoteCard({ note, index }: { note: Note; index: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30, delay: index * 0.04 }}
      className="glass-card rounded-2xl p-4"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-800 text-cyan-300">
          <BookOpen size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-slate-50">{note.title}</h3>
          <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-300">{note.body}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {note.links.map((link) => (
              <span key={link} className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2.5 py-1 text-[11px] text-cyan-200">
                <Link2 size={11} />
                {link}
              </span>
            ))}
          </div>
        </div>
      </div>
    </motion.article>
  );
}
