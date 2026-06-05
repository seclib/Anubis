from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from typing import Any

from registry import ConsoleModule, ModuleRegistry
from modules.rag_client import ModuleRagClient


@dataclass
class SessionContext:
    registry: ModuleRegistry = field(default_factory=ModuleRegistry)
    current_module: ConsoleModule | None = None
    options: dict[str, str] = field(default_factory=dict)
    running: bool = True

    def use(self, module: ConsoleModule) -> None:
        self.current_module = module
        self.options = module.defaults()

    @property
    def prompt(self) -> str:
        if self.current_module:
            return f"anubis ({self.current_module.name}) > "
        return "anubis > "


@dataclass(frozen=True)
class ConsoleResult:
    text: str
    should_continue: bool = True


class ConsoleRouter:
    _exploit_engine = None

    def __init__(self, context: SessionContext | None = None) -> None:
        self.context = context or SessionContext()

    def route(self, line: str) -> ConsoleResult:
        parts = self._split(line)
        if not parts:
            return ConsoleResult("")
        command = parts[0].lower()
        args = parts[1:]

        if command in {"help", "?"}:
            return ConsoleResult(self.help())
        if command in {"exit", "quit", "q"}:
            self.context.running = False
            return ConsoleResult("bye", should_continue=False)
        if command == "show":
            return ConsoleResult(self.show(args))
        if command == "use":
            return ConsoleResult(self.use(args))
        if command == "info":
            return ConsoleResult(self.info(args))
        if command == "set":
            return ConsoleResult(self.set_option(args))
        if command in {"unset", "unsetg"}:
            return ConsoleResult(self.unset_option(args))
        if command == "options":
            return ConsoleResult(self.show(["options"]))
        if command in {"run", "execute"}:
            return ConsoleResult(self.run(args))
        if command == "back":
            return ConsoleResult(self.back())
        if command in {"search", "rag"}:
            return ConsoleResult(self.rag_query(" ".join(args)))
        if command == "exploit":
            return ConsoleResult(self.exploit(args))
        if command == "tools" and args and args[0].lower() in {"start", "stop", "status"}:
            return ConsoleResult(self.optional_tools(args))
        if command in {"osint", "cve", "bugbounty", "bug", "dev", "defense", "graph", "tools"}:
            return ConsoleResult(self.direct_domain_query(command, " ".join(args)))
        return ConsoleResult(f"unknown command: {command}\nrun: help")

    def help(self) -> str:
        return "\n".join(
            [
                "Core Commands",
                "=============",
                "help                      Show this help",
                "show modules              List available modules",
                "show options              Show current module options",
                "use <module>              Select a module",
                "info [module]             Show module details",
                "set <OPTION> <VALUE>      Set module option",
                "unset <OPTION>            Clear module option",
                "run                       Execute current module",
                "back                      Leave current module",
                "search <query>            Route query through ANUBIS RAG router",
                "exploit search <keyword>  Search Exploit-DB intelligence",
                "exploit info <id>         Show indexed exploit details",
                "exploit filter <type>     Filter by RCE/LFI/SQLi/XSS/PrivEsc/SSRF",
                "tools start metasploit    Start optional Metasploit Docker profile",
                "tools start bloodhound    Start optional BloodHound + Neo4j profile",
                "tools stop                Stop optional tool containers",
                "exit                      Quit console",
                "",
                "Direct RAG Commands",
                "===================",
                "osint <query> | cve <query> | bugbounty <query> | dev <query>",
                "defense <query> | graph <query> | tools <query>",
            ]
        )

    def show(self, args: list[str]) -> str:
        subject = args[0].lower() if args else ""
        if subject in {"modules", "module"}:
            rows = ["Available Modules", "================="]
            for module in self.context.registry.list():
                rows.append(f"{module.name:<24} {module.description}")
            return "\n".join(rows)
        if subject in {"options", "opts"}:
            return self.show_options()
        return "usage: show modules | show options"

    def show_options(self) -> str:
        module = self.context.current_module
        if not module:
            return "no module selected\nuse <module>"
        rows = [f"Module options ({module.name})", "=" * (17 + len(module.name)), "Name       Required  Current  Description"]
        for option in module.options:
            current = self.context.options.get(option.name, "") or ""
            required = "yes" if option.required else "no"
            rows.append(f"{option.name:<10} {required:<8} {current:<8} {option.description}")
        return "\n".join(rows)

    def use(self, args: list[str]) -> str:
        if not args:
            return "usage: use <module>"
        module = self.context.registry.get(args[0])
        if not module:
            return f"module not found: {args[0]}\nrun: show modules"
        self.context.use(module)
        return f"using {module.name}"

    def info(self, args: list[str]) -> str:
        module = self.context.registry.get(args[0]) if args else self.context.current_module
        if not module:
            return "no module selected\nusage: info <module>"
        aliases = [name for name in {module.name, module.domain}]
        return "\n".join(
            [
                f"Name: {module.name}",
                f"Domain: {module.domain}",
                f"Description: {module.description}",
                f"Aliases: {', '.join(aliases)}",
                "",
                self._options_for(module),
            ]
        )

    def set_option(self, args: list[str]) -> str:
        if not self.context.current_module:
            return "no module selected\nuse <module>"
        if len(args) < 2:
            return "usage: set <OPTION> <VALUE>"
        key = args[0].upper()
        value = " ".join(args[1:]).strip()
        valid = {option.name for option in self.context.current_module.options}
        if key not in valid:
            return f"unknown option: {key}\nrun: show options"
        self.context.options[key] = value
        return f"{key} => {value}"

    def unset_option(self, args: list[str]) -> str:
        if not args:
            return "usage: unset <OPTION>"
        key = args[0].upper()
        self.context.options.pop(key, None)
        return f"{key} cleared"

    def back(self) -> str:
        if not self.context.current_module:
            return "no module selected"
        previous = self.context.current_module.name
        self.context.current_module = None
        self.context.options.clear()
        return f"left {previous}"

    def run(self, args: list[str]) -> str:
        module = self.context.current_module
        if not module:
            return "no module selected\nuse <module>"
        missing = module.validate(self.context.options)
        if missing:
            return "missing required options: " + ", ".join(missing) + "\nrun: show options"
        runtime_options = dict(self.context.options)
        if args:
            runtime_options["QUERY"] = " ".join(args).strip()
        try:
            return ModuleRagClient().format_cli(module.run(runtime_options))
        except Exception as exc:
            return f"{module.name} failed: {exc}"

    def rag_query(self, query: str) -> str:
        if not query.strip():
            return "usage: search <query>"
        try:
            client = ModuleRagClient()
            return client.format_cli(client.route(query))
        except Exception as exc:
            return f"rag routing failed: {exc}"

    def direct_domain_query(self, command: str, query: str) -> str:
        module = self.context.registry.get(command)
        domain = module.domain if module else command
        if domain == "defense":
            domain = "cyberdefense"
        if not query.strip():
            return f"usage: {command} <query>"
        return self.query_domain(domain, query, {})

    def exploit(self, args: list[str]) -> str:
        if not args:
            return "\n".join(
                [
                    "usage:",
                    "  exploit search <keyword>",
                    "  exploit info <id>",
                    "  exploit filter <RCE|LFI|SQLi|XSS|PrivEsc|SSRF>",
                ]
            )
        action = args[0].lower()
        payload = " ".join(args[1:]).strip()
        engine = self._exploit_engine_instance()
        if action == "search":
            if not payload:
                return "usage: exploit search <keyword>"
            results = engine.search(payload, limit=10)
            return self._format_exploit_results(f"Exploit search: {payload}", results, engine)
        if action == "info":
            if not payload:
                return "usage: exploit info <id>"
            return engine.cli_info(engine.get(payload))
        if action == "filter":
            if not payload:
                return "usage: exploit filter <RCE|LFI|SQLi|XSS|PrivEsc|SSRF>"
            results = engine.filter_by_type(payload, limit=20)
            return self._format_exploit_results(f"Exploit filter: {payload}", results, engine)
        return f"unknown exploit action: {action}\nusage: exploit search|info|filter"

    def optional_tools(self, args: list[str]) -> str:
        try:
            from tools.optional_stack import OptionalToolStack
        except Exception as exc:
            return f"optional tools unavailable: {exc}"

        stack = OptionalToolStack()
        action = args[0].lower() if args else ""
        target = args[1].lower() if len(args) > 1 else ""

        try:
            if action == "start" and target == "metasploit":
                return stack.start_metasploit().render()
            if action == "start" and target == "bloodhound":
                return stack.start_bloodhound().render()
            if action == "stop":
                return stack.stop().render()
            if action == "status":
                return stack.status().render()
        except Exception as exc:
            return f"optional tools command failed: {exc}"

        return "\n".join(
            [
                "usage:",
                "  tools start metasploit",
                "  tools start bloodhound",
                "  tools stop",
                "  tools status",
            ]
        )

    def query_domain(self, domain: str, query: str, filters: dict[str, str] | None = None) -> str:
        try:
            client = ModuleRagClient()
            return client.format_cli(client.search_domain(domain, query, self._filters(filters or {})))
        except Exception as exc:
            return f"{domain} retrieval failed: {exc}"

    def _exploit_engine_instance(self):
        if self.__class__._exploit_engine is None:
            from rag_exploitdb.search_engine import ExploitDbSearchEngine

            self.__class__._exploit_engine = ExploitDbSearchEngine()
        return self.__class__._exploit_engine

    def _format_exploit_results(self, title: str, results: list[Any], engine: Any) -> str:
        lines = [title, "=" * len(title), f"results={len(results)}", ""]
        lines.append(engine.cli_summary(results))
        return "\n".join(lines).rstrip()

    def _query_from_context(self, module: ConsoleModule) -> str:
        values = [self.context.options.get(option.name, "") for option in module.options]
        query = " ".join(value for value in values if value).strip()
        return query or module.description

    def _filters(self, values: dict[str, str]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if values.get("CVE"):
            filters["cves"] = [values["CVE"]]
        if values.get("TARGET"):
            filters["targets"] = [values["TARGET"]]
        if values.get("DOMAIN"):
            filters["domains"] = [values["DOMAIN"]]
        if values.get("TECHNIQUE"):
            filters["mitre_techniques"] = [values["TECHNIQUE"]]
        if values.get("TOOL"):
            filters["tools"] = [values["TOOL"]]
        return filters

    def _options_for(self, module: ConsoleModule) -> str:
        rows = ["Options:", "Name       Required  Default  Description"]
        for option in module.options:
            rows.append(
                f"{option.name:<10} {'yes' if option.required else 'no':<8} {(option.default or ''):<8} {option.description}"
            )
        return "\n".join(rows)

    def _split(self, line: str) -> list[str]:
        try:
            return shlex.split(line.strip())
        except ValueError:
            return line.strip().split()
