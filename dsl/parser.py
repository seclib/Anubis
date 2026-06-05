from __future__ import annotations

import shlex
from typing import Any

from anubis.dsl.ast import AgentNode, CommandNode, PipelineNode, SwarmNode, ToolNode
from anubis.dsl.lexer import split_pipeline, tokenize


class DslParseError(ValueError):
    pass


class DslParser:
    def parse(self, text: str) -> dict[str, Any]:
        source = text.strip()
        if not source:
            return CommandNode(command="", args="", argv=[]).to_dict()

        parts = split_pipeline(source)
        if len(parts) > 1:
            return PipelineNode(steps=[self.parse(part) for part in parts]).to_dict()

        if source.startswith("/swarm") and "{" in source:
            return self._parse_swarm_block(source).to_dict()

        if source.startswith("/agent"):
            return self._parse_agent_command(source).to_dict()

        if source.startswith("/tool"):
            return self._parse_tool_call(source).to_dict()

        return self._parse_command(source).to_dict()

    def _parse_command(self, source: str) -> CommandNode:
        argv = _argv(source)
        if not argv:
            return CommandNode(command="", args="", argv=[])
        command = argv[0]
        args = source[len(command) :].strip()
        return CommandNode(command=command, args=args, argv=argv[1:])

    def _parse_agent_command(self, source: str) -> AgentNode:
        body = source[len("/agent") :].strip()
        if ":" not in body:
            command = self._parse_command(source)
            return AgentNode(agent="", task=command.args)
        agent, task = body.split(":", 1)
        return AgentNode(agent=agent.strip(), task=task.strip())

    def _parse_swarm_block(self, source: str) -> SwarmNode:
        start = source.find("{")
        end = source.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise DslParseError("invalid swarm block")

        body = source[start + 1 : end].strip()
        tasks: list[dict[str, Any]] = []
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            if ":" not in line:
                if "|" in line:
                    tasks.append(self.parse(line))
                    continue
                tasks.append(CommandNode(command="/task", args=line, argv=_argv(line)).to_dict())
                continue
            agent, task = line.split(":", 1)
            task_text = task.strip()
            task_value: Any = self.parse(task_text) if "|" in task_text else task_text
            tasks.append(AgentNode(agent=agent.strip(), task=task_value).to_dict())
        return SwarmNode(tasks=tasks)

    def _parse_tool_call(self, source: str) -> ToolNode:
        argv = _argv(source)
        if len(argv) < 2:
            raise DslParseError("tool name required")
        tool = argv[1]
        action = argv[2] if len(argv) >= 3 else ""
        args = argv[3:]
        payload = _tool_payload(tool, action, args)
        return ToolNode(tool=tool, action=action, args=args, payload=payload)


def parse_dsl(text: str) -> dict[str, Any]:
    return DslParser().parse(text)


def _argv(source: str) -> list[str]:
    try:
        return [token.value for token in tokenize(source)]
    except ValueError:
        try:
            return shlex.split(source)
        except ValueError:
            return source.split()


def _tool_payload(tool: str, action: str, args: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"tool": tool, "action": action}
    if tool == "github":
        if action == "create_repo" and args:
            payload["name"] = args[0]
        elif action in {"list_issues", "commit"} and args:
            payload["repo"] = args[0]
        if action == "commit" and len(args) > 1:
            payload["message"] = " ".join(args[1:])
    elif tool == "filesystem":
        if action in {"read", "read_file"} and args:
            payload["action"] = "read_file"
            payload["path"] = args[0]
        elif action in {"write", "write_file"}:
            payload["action"] = "write_file"
            if args:
                payload["path"] = args[0]
            if len(args) > 1:
                payload["content"] = " ".join(args[1:])
        elif action in {"list", "list_directory"}:
            payload["action"] = "list_directory"
            payload["path"] = args[0] if args else "."
    elif tool == "web":
        if action == "search":
            payload["query"] = " ".join(args)
        elif action == "fetch" and args:
            payload["url"] = args[0]
    else:
        payload["args"] = args
    return payload


__all__ = ["DslParseError", "DslParser", "parse_dsl"]
