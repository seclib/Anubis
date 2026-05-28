"""Dedicated testing agent contract and validation helpers."""

from __future__ import annotations

import json
from typing import Any

TESTER_AGENT = "tester_agent"

TESTER_RESPONSIBILITIES = [
    "execute_tests",
    "run_validation_commands",
    "detect_runtime_errors",
    "verify_results",
]

TESTER_RULES = [
    "analyze shell outputs",
    "return structured errors",
    "generate validation reports",
    "separate runtime errors from assertion failures",
    "recommend the next validation command when evidence is incomplete",
]

TESTER_REPORT_SCHEMA = {
    "success": "boolean",
    "status": "passed | failed | inconclusive",
    "summary": "short validation summary",
    "commands": ["commands inspected or recommended"],
    "errors": [
        {
            "type": "runtime | assertion | command | environment | unknown",
            "message": "error message",
            "command": "related command if any",
            "evidence": "relevant stdout/stderr excerpt",
        }
    ],
    "next_action": "continue | fix | run_command | complete",
}

TESTER_PROMPT = """You are tester_agent, the validation specialist of Anubis.

Responsibilities:
- Execute tests.
- Run validation commands.
- Detect runtime errors.
- Verify results.

Validation rules:
- Analyze shell outputs carefully.
- Return structured errors.
- Generate a validation report.
- Separate runtime errors, assertion failures, command failures, and environment issues.
- If evidence is incomplete, recommend the next validation command.
- Do not ask humans for help.

Return JSON compatible with this schema:
{
  "success": true,
  "status": "passed | failed | inconclusive",
  "summary": "...",
  "commands": ["..."],
  "errors": [
    {
      "type": "runtime | assertion | command | environment | unknown",
      "message": "...",
      "command": "...",
      "evidence": "..."
    }
  ],
  "next_action": "continue | fix | run_command | complete"
}"""


def create_tester_state() -> dict[str, Any]:
    return {
        "agent": TESTER_AGENT,
        "responsibilities": TESTER_RESPONSIBILITIES,
        "rules": TESTER_RULES,
        "report_schema": TESTER_REPORT_SCHEMA,
        "status": "ready",
    }


def build_tester_context(memory: dict[str, Any]) -> str:
    tester_state = memory.get("tester_agent")
    if not isinstance(tester_state, dict):
        tester_state = create_tester_state()
        memory["tester_agent"] = tester_state

    return (
        "Tester agent contract:\n"
        + "\n".join(f"- {item}" for item in TESTER_RESPONSIBILITIES)
        + "\n\nTester rules:\n"
        + "\n".join(f"- {item}" for item in TESTER_RULES)
        + "\n\nValidation report schema:\n"
        + json.dumps(TESTER_REPORT_SCHEMA, ensure_ascii=False, indent=2)
    )


def normalize_validation_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "success": False,
            "status": "inconclusive",
            "summary": "Tester output was not structured JSON",
            "commands": [],
            "errors": [
                {
                    "type": "unknown",
                    "message": str(value),
                    "command": "",
                    "evidence": "",
                }
            ],
            "next_action": "fix",
        }

    errors = value.get("errors", [])
    if not isinstance(errors, list):
        errors = [errors]

    commands = value.get("commands", [])
    if not isinstance(commands, list):
        commands = [commands]

    status = str(value.get("status", "passed" if value.get("success") else "failed"))
    if status not in {"passed", "failed", "inconclusive"}:
        status = "inconclusive"

    return {
        "success": bool(value.get("success", status == "passed")),
        "status": status,
        "summary": str(value.get("summary", value.get("reason", ""))),
        "commands": [str(command) for command in commands if str(command).strip()],
        "errors": [
            error
            if isinstance(error, dict)
            else {
                "type": "unknown",
                "message": str(error),
                "command": "",
                "evidence": "",
            }
            for error in errors
        ],
        "next_action": str(value.get("next_action", "complete" if value.get("success") else "fix")),
    }


__all__ = [
    "TESTER_AGENT",
    "TESTER_PROMPT",
    "TESTER_REPORT_SCHEMA",
    "TESTER_RESPONSIBILITIES",
    "TESTER_RULES",
    "build_tester_context",
    "create_tester_state",
    "normalize_validation_report",
]
