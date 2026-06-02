import {
  Bot,
  FileSearch,
  FileText,
  GitCommit,
  Plug,
  Search,
  Settings2,
  TerminalSquare,
} from "lucide-react";
import type { CommandDefinition, CommandRequirement } from "./types";
import type { PluginManifest } from "../api";

const runtimeOnline: CommandRequirement = {
  id: "runtime-online",
  label: "Requires local runtime",
  test: (context) => context.runtimeHealth.status === "online",
};

const projectOpen: CommandRequirement = {
  id: "project-open",
  label: "Requires an open project",
  test: (context) => context.projectOpen,
};

const hasGitChanges: CommandRequirement = {
  id: "git-dirty",
  label: "Requires git changes",
  test: (context) => context.gitDirty,
};

const hasPlugins: CommandRequirement = {
  id: "plugins-available",
  label: "Requires local plugins",
  test: (context) => context.plugins.length > 0,
};

export function buildCommandRegistry(plugins: PluginManifest[]): CommandDefinition[] {
  return [
    {
      id: "core.run-agent",
      label: "Run Agent",
      description: "Send the current prompt to the ANUBIS agent runtime",
      group: "Core",
      keywords: ["chat", "ask", "execute", "/run"],
      icon: <Bot size={16} />,
      requirements: [runtimeOnline],
      action: async (helpers, context) => {
        await helpers.runAgent(context.input || undefined);
      },
    },
    {
      id: "core.open-file",
      label: "Open File",
      description: "Prepare a local file request",
      group: "Core",
      keywords: ["filesystem", "path", "/file"],
      icon: <FileText size={16} />,
      requirements: [projectOpen],
      action: (helpers) => {
        helpers.setPrompt("/file ");
        helpers.focusChat();
      },
    },
    {
      id: "core.search-vault",
      label: "Search Vault",
      description: "Search local notes and memory context",
      group: "Core",
      keywords: ["memory", "obsidian", "notes", "/context"],
      icon: <Search size={16} />,
      requirements: [runtimeOnline],
      action: (helpers) => {
        helpers.setPrompt("/context ");
        helpers.focusChat();
      },
    },
    {
      id: "core.run-shell-command",
      label: "Run Shell Command",
      description: "Prepare a sandboxed shell execution request",
      group: "Tools",
      keywords: ["terminal", "bash", "command", "/run"],
      icon: <TerminalSquare size={16} />,
      requirements: [runtimeOnline, projectOpen],
      action: (helpers) => {
        helpers.setPrompt("/run ");
        helpers.focusChat();
      },
    },
    {
      id: "core.git-commit",
      label: "Git Commit",
      description: "Create a local commit from current project changes",
      group: "Project",
      keywords: ["version control", "changes", "/git"],
      icon: <GitCommit size={16} />,
      requirements: [runtimeOnline, projectOpen, hasGitChanges],
      action: (helpers) => {
        helpers.setPrompt("/git commit ");
        helpers.focusChat();
      },
    },
    {
      id: "core.toggle-plugin",
      label: "Toggle Plugin",
      description: "Choose a local plugin to enable or disable",
      group: "Plugins",
      keywords: ["extension", "module"],
      icon: <Plug size={16} />,
      requirements: [hasPlugins],
      action: (helpers, context) => {
        const plugin = context.plugins[0];
        if (plugin) {
          helpers.togglePlugin(plugin.name);
        }
      },
    },
    {
      id: "core.settings",
      label: "Settings",
      description: "Open local runtime preferences",
      group: "Core",
      keywords: ["preferences", "config"],
      icon: <Settings2 size={16} />,
      action: (helpers) => {
        helpers.appendSystemNote("Settings command selected.");
      },
    },
    ...plugins.map(pluginCommand),
  ];
}

function pluginCommand(plugin: PluginManifest): CommandDefinition {
  return {
    id: `plugin.toggle.${plugin.name}`,
    label: `Toggle ${plugin.displayName}`,
    description: plugin.description || `Toggle ${plugin.name}`,
    group: "Plugins",
    keywords: ["plugin", plugin.name, ...plugin.triggers],
    icon: <FileSearch size={16} />,
    action: (helpers) => helpers.togglePlugin(plugin.name),
  };
}
