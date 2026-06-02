import type { CommandDefinition, CommandContext, ResolvedCommand } from "./types";

export function resolveCommands(
  commands: CommandDefinition[],
  context: CommandContext,
  query: string,
): ResolvedCommand[] {
  const normalizedQuery = normalize(query);

  return commands
    .map((command) => {
      const failedRequirement = command.requirements?.find((requirement) => !requirement.test(context));
      return {
        ...command,
        enabled: !failedRequirement,
        disabledReason: failedRequirement?.label,
        score: scoreCommand(command, normalizedQuery),
      };
    })
    .filter((command) => !normalizedQuery || command.score > 0)
    .sort((left, right) => {
      if (left.enabled !== right.enabled) {
        return left.enabled ? -1 : 1;
      }
      return right.score - left.score || left.label.localeCompare(right.label);
    });
}

function scoreCommand(command: CommandDefinition, query: string): number {
  if (!query) {
    return 1;
  }

  const haystack = normalize(
    [command.label, command.description, command.group, ...(command.keywords ?? [])].join(" "),
  );

  if (haystack.includes(query)) {
    return 100 + query.length / Math.max(haystack.length, 1);
  }

  let score = 0;
  let queryIndex = 0;
  let streak = 0;

  for (let index = 0; index < haystack.length && queryIndex < query.length; index += 1) {
    if (haystack[index] !== query[queryIndex]) {
      streak = 0;
      continue;
    }

    streak += 1;
    score += 8 + streak * 2;
    if (index === 0 || haystack[index - 1] === " ") {
      score += 6;
    }
    queryIndex += 1;
  }

  return queryIndex === query.length ? score : 0;
}

function normalize(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}
