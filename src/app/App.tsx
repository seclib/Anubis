import React, { FormEvent, useEffect, useMemo, useRef } from "react";
import { Shell } from "./layout/Shell";
import { Chat } from "./ui/Chat";
import { CommandPalette } from "./ui/CommandPalette";
import { InputBar } from "./ui/InputBar";
import { buildCommandRegistry } from "./core/commands/registry";
import type { CommandActionHelpers, CommandContext } from "./core/commands/types";
import { loadModules } from "./core/modules/moduleHost";
import { selectEffectivePlugins, useAnubisStore } from "./state/anubisStore";
import "./ui/styles.css";

export default function App() {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messages = useAnubisStore((state) => state.messages);
  const input = useAnubisStore((state) => state.input);
  const busy = useAnubisStore((state) => state.busy);
  const health = useAnubisStore((state) => state.health);
  const paletteOpen = useAnubisStore((state) => state.paletteOpen);
  const plugins = useAnubisStore((state) => state.plugins);
  const pluginOverrides = useAnubisStore((state) => state.pluginOverrides);
  const moduleRuntime = useAnubisStore((state) => state.moduleRuntime);
  const appendSystemNote = useAnubisStore((state) => state.appendSystemNote);
  const closePalette = useAnubisStore((state) => state.closePalette);
  const refreshRuntime = useAnubisStore((state) => state.refreshRuntime);
  const runAgent = useAnubisStore((state) => state.runAgent);
  const setInput = useAnubisStore((state) => state.setInput);
  const setModuleRuntime = useAnubisStore((state) => state.setModuleRuntime);
  const togglePalette = useAnubisStore((state) => state.togglePalette);
  const togglePlugin = useAnubisStore((state) => state.togglePlugin);

  useEffect(() => {
    void refreshRuntime();
    const interval = window.setInterval(refreshRuntime, 15000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        togglePalette();
        return;
      }

      if (event.key === "Escape") {
        closePalette();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closePalette, togglePalette]);

  const effectivePlugins = useMemo(
    () => selectEffectivePlugins({ plugins, pluginOverrides }),
    [plugins, pluginOverrides],
  );

  const commandHelpers: CommandActionHelpers = useMemo(
    () => ({
      appendSystemNote,
      focusChat: () => inputRef.current?.focus(),
      refreshRuntime,
      runAgent: async (prompt?: string) => {
        await runAgent(prompt);
        inputRef.current?.focus();
      },
      setPrompt: setInput,
      togglePlugin,
    }),
    [appendSystemNote, refreshRuntime, runAgent, setInput, togglePlugin],
  );

  useEffect(() => {
    let cancelled = false;

    async function refreshModules() {
      const runtime = await loadModules(effectivePlugins, commandHelpers);
      if (!cancelled) {
        setModuleRuntime(runtime);
      }
    }

    void refreshModules();

    if (import.meta.hot) {
      import.meta.hot.accept(() => {
        void refreshModules();
      });
    }

    return () => {
      cancelled = true;
    };
  }, [commandHelpers, effectivePlugins, setModuleRuntime]);

  async function submitPrompt(event?: FormEvent) {
    event?.preventDefault();
    await runAgent(input);
    inputRef.current?.focus();
  }

  const commandContext: CommandContext = useMemo(
    () => ({
      runtimeHealth: health,
      plugins: effectivePlugins,
      input,
      busy,
      projectOpen: true,
      gitDirty: true,
    }),
    [busy, effectivePlugins, health, input],
  );

  const commands = useMemo(
    () => [...buildCommandRegistry(effectivePlugins), ...moduleRuntime.commands],
    [effectivePlugins, moduleRuntime.commands],
  );

  return (
    <Shell>
      <Chat messages={messages} busy={busy} scrollerRef={scrollerRef} />
      <InputBar value={input} busy={busy} inputRef={inputRef} onChange={setInput} onSubmit={submitPrompt} />

      <CommandPalette
        open={paletteOpen}
        commands={commands}
        context={commandContext}
        helpers={commandHelpers}
        onClose={closePalette}
      />
    </Shell>
  );
}
