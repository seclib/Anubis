import type { CommandActionHelpers } from "../commands/types";
import type {
  AnubisModuleApi,
  ModuleChatAction,
  ModuleCommand,
  ModuleManifest,
  ModuleRuntimeState,
  ModuleTool,
} from "./moduleTypes";

type MutableModuleState = {
  chatActions: ModuleChatAction[];
  commands: ModuleCommand[];
  loaded: ModuleManifest[];
  tools: ModuleTool[];
};

export function createModuleRegistry(helpers: CommandActionHelpers) {
  const state: MutableModuleState = {
    chatActions: [],
    commands: [],
    loaded: [],
    tools: [],
  };

  function assertPermission(module: ModuleManifest, permission: string) {
    if (!module.permissions?.includes(permission as never)) {
      throw new Error(`${module.name} requires "${permission}" permission`);
    }
  }

  function apiFor(module: ModuleManifest): AnubisModuleApi {
    return {
      registerCommand(command) {
        assertPermission(module, "commands");
        state.commands.push(prefixCommand(module, command));
      },
      addChatAction(action) {
        assertPermission(module, "chat");
        state.chatActions.push(prefixChatAction(module, action));
      },
      registerTool(tool) {
        assertPermission(module, "tools");
        state.tools.push(prefixTool(module, tool));
      },
      core: {
        async chat(message) {
          assertPermission(module, "chat");
          await helpers.runAgent(message);
        },
        async readFile(path) {
          assertPermission(module, "files");
          helpers.appendSystemNote(`${module.name} requested file read: ${path}`);
          return "";
        },
        async writeFile(path, content) {
          assertPermission(module, "files");
          helpers.appendSystemNote(`${module.name} requested file write: ${path} (${content.length} chars)`);
        },
        async runTool(toolId, input) {
          assertPermission(module, "tools");
          const tool = state.tools.find((item) => item.id === toolId || item.id === `${module.name}.${toolId}`);
          if (!tool) {
            throw new Error(`Unknown module tool: ${toolId}`);
          }
          return tool.run(input);
        },
      },
    };
  }

  function snapshot(): ModuleRuntimeState {
    return {
      chatActions: [...state.chatActions],
      commands: state.commands.map((command) => ({
        id: command.id,
        label: command.label,
        description: command.description || "Module command",
        group: "Plugins",
        keywords: ["module", ...(command.keywords ?? [])],
        icon: null,
        action: async () => {
          await command.run();
        },
      })),
      loaded: [...state.loaded],
      tools: [...state.tools],
    };
  }

  return {
    apiFor,
    markLoaded(module: ModuleManifest) {
      state.loaded.push(module);
    },
    snapshot,
  };
}

function prefixCommand(module: ModuleManifest, command: ModuleCommand): ModuleCommand {
  return {
    ...command,
    id: command.id.startsWith(`${module.name}.`) ? command.id : `${module.name}.${command.id}`,
  };
}

function prefixChatAction(module: ModuleManifest, action: ModuleChatAction): ModuleChatAction {
  return {
    ...action,
    id: action.id.startsWith(`${module.name}.`) ? action.id : `${module.name}.${action.id}`,
  };
}

function prefixTool(module: ModuleManifest, tool: ModuleTool): ModuleTool {
  return {
    ...tool,
    id: tool.id.startsWith(`${module.name}.`) ? tool.id : `${module.name}.${tool.id}`,
  };
}
