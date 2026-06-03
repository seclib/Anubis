import { KeyboardEvent, memo, RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";
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

export const CommandPalette = memo(function CommandPalette({ open, commands, context, helpers, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const activeItemRef = useRef<HTMLButtonElement>(null);

  const results = useMemo(() => resolveCommands(commands, context, query), [commands, context, query]);
  const executableResults = useMemo(() => results.filter((command) => command.enabled), [results]);

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

  const execute = useCallback(async (command: ResolvedCommand | undefined) => {
    if (!command || !command.enabled) {
      return;
    }

    onClose();
    setQuery("");
    setActiveIndex(0);
    await command.action(helpers, context);
  }, [context, helpers, onClose]);

  if (!open) {
    return null;
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
            <CommandPaletteItem
              active={index === activeIndex}
              activeItemRef={activeItemRef}
              command={command}
              index={index}
              key={command.id}
              onExecute={execute}
              onFocusIndex={setActiveIndex}
            />
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
});

type CommandPaletteItemProps = {
  active: boolean;
  activeItemRef: RefObject<HTMLButtonElement>;
  command: ResolvedCommand;
  index: number;
  onExecute: (command: ResolvedCommand | undefined) => Promise<void>;
  onFocusIndex: (index: number) => void;
};

const CommandPaletteItem = memo(function CommandPaletteItem({
  active,
  activeItemRef,
  command,
  index,
  onExecute,
  onFocusIndex,
}: CommandPaletteItemProps) {
  return (
    <button
      id={command.id}
      ref={active ? activeItemRef : undefined}
      className={active ? "active" : ""}
      type="button"
      role="option"
      aria-selected={active}
      aria-disabled={!command.enabled}
      disabled={!command.enabled}
      onMouseEnter={() => onFocusIndex(index)}
      onClick={() => void onExecute(command)}
    >
      {command.icon}
      <span>
        <strong>{command.label}</strong>
        <small>{command.enabled ? command.description : command.disabledReason}</small>
      </span>
      <em>{command.group}</em>
    </button>
  );
});
