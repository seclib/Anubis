import type { CommandActionHelpers } from "../commands/types";
import { createModuleRegistry } from "./moduleRegistry";
import type { ModuleEntrypoint, ModuleManifest, ModuleRuntimeState } from "./moduleTypes";

const moduleLoaders = import.meta.glob<ModuleEntrypoint>("../../../../plugins/*/index.ts");

export async function loadModules(
  manifests: ModuleManifest[],
  helpers: CommandActionHelpers,
): Promise<ModuleRuntimeState> {
  const registry = createModuleRegistry(helpers);

  for (const manifest of manifests) {
    if (!manifest.enabled || !manifest.entry) {
      continue;
    }

    const loader = moduleLoaderFor(manifest);
    if (!loader) {
      helpers.appendSystemNote(`Module ${manifest.name} has no bundled entry: ${manifest.entry}`);
      continue;
    }

    const entrypoint = await loader();
    await entrypoint.default(registry.apiFor(manifest));
    registry.markLoaded(manifest);
  }

  return registry.snapshot();
}

export function moduleHotReloadSignature() {
  return Object.keys(moduleLoaders).join(":");
}

function moduleLoaderFor(manifest: ModuleManifest) {
  const folderName = folderNameFromSource(manifest.source) || manifest.name;
  const expectedSuffix = `/plugins/${folderName}/${manifest.entry || "index.ts"}`;

  return Object.entries(moduleLoaders).find(([path]) => path.endsWith(expectedSuffix))?.[1];
}

function folderNameFromSource(source: string) {
  const normalized = source.replace(/\\/g, "/");
  const match = normalized.match(/(?:^|\/)plugins\/([^/]+)\/(?:manifest|plugin)\.json$/);
  return match?.[1];
}
