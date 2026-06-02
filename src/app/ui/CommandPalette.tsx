import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Command, FileText, Settings2, TerminalSquare } from "lucide-react";
import { resolveCommands } from "../core/commands/fuzzy";
import type { CommandActionHelpers, CommandContext, CommandDefinition, ResolvedCommand } from "../core/commands/types";

type CommandPaletteProps = {
  open: boolean;
  commands: CommandDefinition[];
  context: CommandContext;
  helpers: CommandActionHelpers;
  onClose: () => void;
};

export function CommandPalette({ open, commands, context, helpers, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const activeItemRef = useRef<HTMLButtonElement>(null);

  const results = useMemo(() => resolveCommands(commands, context, query), [commands, context, query]);
  const executableResults = results.filter((command) => command.enabled);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(0);
      return;
    }

    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(results.length - 1, 0)));
  }, [results.length]);

  useEffect(() => {
    activeItemRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!open) {
    return null;
  }

  async function execute(command: ResolvedCommand | undefined) {
    if (!command || !command.enabled) {
      return;
    }

    onClose();
    setQuery("");
    setActiveIndex(0);
    await command.action(helpers, context);
  }

  function onPaletteKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (results.length ? (current + 1) % results.length : 0));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (results.length ? (current - 1 + results.length) % results.length : 0));
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(Math.max(results.length - 1, 0));
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      const activeCommand = results[activeIndex];
      void execute(activeCommand?.enabled ? activeCommand : executableResults[0]);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  }

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <section className="palette" onMouseDown={(event) => event.stopPropagation()} aria-label="Command palette">
        <div className="palette-search">
          <Command size={17} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onPaletteKeyDown}
            placeholder="Search commands..."
            aria-activedescendant={results[activeIndex]?.id}
          />
        </div>
        <div className="palette-list" role="listbox">
          {results.map((command, index) => (
            <button
              id={command.id}
              ref={index === activeIndex ? activeItemRef : undefined}
              className={index === activeIndex ? "active" : ""}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              aria-disabled={!command.enabled}
              disabled={!command.enabled}
              key={command.id}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => void execute(command)}
            >
              {command.icon}
              <span>
                <strong>{command.label}</strong>
                <small>{command.enabled ? command.description : command.disabledReason}</small>
              </span>
              <em>{command.group}</em>
            </button>
          ))}
          {!results.length && <div className="empty-state">No matching command</div>}
        </div>
        <footer>
          <span><TerminalSquare size={14} /> Execute instantly</span>
          <span><FileText size={14} /> Context-aware</span>
          <span><Settings2 size={14} /> Registry-backed</span>
        </footer>
      </section>
    </div>
  );
}
