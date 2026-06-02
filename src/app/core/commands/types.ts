import type { ReactNode } from "react";
import type { PluginManifest, RuntimeHealth } from "../api";

export type CommandContext = {
  runtimeHealth: RuntimeHealth;
  plugins: PluginManifest[];
  input: string;
  busy: boolean;
  projectOpen: boolean;
  gitDirty: boolean;
};

export type CommandRequirement = {
  id: string;
  label: string;
  test: (context: CommandContext) => boolean;
};

export type CommandActionHelpers = {
  appendSystemNote: (content: string) => void;
  focusChat: () => void;
  refreshRuntime: () => Promise<void>;
  runAgent: (prompt?: string) => Promise<void>;
  setPrompt: (value: string) => void;
  togglePlugin: (pluginName: string) => void;
};

export type CommandDefinition = {
  id: string;
  label: string;
  description: string;
  group: "Core" | "Project" | "Tools" | "Plugins";
  keywords?: string[];
  icon: ReactNode;
  requirements?: CommandRequirement[];
  action: (helpers: CommandActionHelpers, context: CommandContext) => void | Promise<void>;
};

export type ResolvedCommand = CommandDefinition & {
  enabled: boolean;
  disabledReason?: string;
  score: number;
};
