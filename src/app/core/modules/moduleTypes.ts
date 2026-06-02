import type { CommandDefinition } from "../commands/types";
import type { PluginManifest } from "../api";

export type ModulePermission = "chat" | "commands" | "files" | "tools" | "ui";

export type ModuleManifest = PluginManifest & {
  entry?: string;
  permissions?: ModulePermission[];
  version?: string;
};

export type ModuleCommand = {
  id: string;
  label: string;
  description?: string;
  keywords?: string[];
  run: () => void | Promise<void>;
};

export type ModuleChatAction = {
  id: string;
  label: string;
  run: (message: string) => void | Promise<void>;
};

export type ModuleTool = {
  id: string;
  description: string;
  run: (input: unknown) => unknown | Promise<unknown>;
};

export type AnubisModuleApi = {
  registerCommand: (command: ModuleCommand) => void;
  addChatAction: (action: ModuleChatAction) => void;
  registerTool: (tool: ModuleTool) => void;
  core: {
    chat: (message: string) => Promise<void>;
    readFile: (path: string) => Promise<string>;
    writeFile: (path: string, content: string) => Promise<void>;
    runTool: (toolId: string, input: unknown) => Promise<unknown>;
  };
};

export type ModuleEntrypoint = {
  default: (api: AnubisModuleApi) => void | Promise<void>;
};

export type ModuleRuntimeState = {
  chatActions: ModuleChatAction[];
  commands: CommandDefinition[];
  loaded: ModuleManifest[];
  tools: ModuleTool[];
};
