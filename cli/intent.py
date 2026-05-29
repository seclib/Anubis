from __future__ import annotations

import re
from typing import Any

INTENT_MAP = [
    (r"^(scan|nmap)\s+(ports?\s+|network\s+)?(?P<target>\S+)", "run_command", lambda m: {"cmd": f"nmap -F {m['target']}"}),
    (r"^(analyze|lint|audit)\s+(?P<file>\S+)", "run_command", lambda m: {"cmd": f"ruff check {m['file']} 2>/dev/null || python3 -m py_compile {m['file']}"}),
    (r"^(read|cat|show)\s+(?P<path>\S+)", "read_file", lambda m: {"path": m["path"]}),
    (r"^(find|search|grep)\s+(?P<query>.+)", "search_code", lambda m: {"query": m["query"]}),
    (r"^(tree|ls)\s*(?P<path>\S*)", "get_file_tree", lambda m: {"path": m.get("path") or "."}),
    (r"^(status|state)\s*$", "_status", None),
    (r"^(docker)\s+(ps|status)", "run_command", lambda m: {"cmd": "docker ps --format 'table {{.Names}}\\t{{.Status}}'"}),
    (r"^(memory|remember)\s+(?P<fact>.+)", "store_hermes_memory", lambda m: {"summary": m["fact"]}),
    (r"^(git)\s+(?P<sub>status|log|diff)", "run_command", lambda m: {"cmd": f"git {m['sub']}" + (" -n 10 --oneline" if m["sub"] == "log" else "")}),
]


def parse_intent(user_input: str) -> tuple[str, dict[str, Any]] | None:
    for pattern, action, args_fn in INTENT_MAP:
        match = re.match(pattern, user_input, re.IGNORECASE)
        if match:
            args = args_fn(match.groupdict()) if args_fn else {}
            return action, args
    return None

