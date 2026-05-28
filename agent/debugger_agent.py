"""Dedicated debugging agent contract and failure analysis helpers."""

from __future__ import annotations

import json
from typing import Any

DEBUGGER_AGENT = "debugger_agent"

DEBUGGER_RESPONSIBILITIES = [
    "analyze_stack_traces",
    "identify_probable_causes",
    "propose_corrections",
    "rerun_fixes_automatically",
]

DEBUGGER_RULES = [
    "remain autonomous",
    "turn every failure into a concrete retry or strategy change",
    "prefer root-cause fixes over surface patches",
    "preserve the failing evidence in structured form",
    "never ask for human help",
]

DEBUGGER_REPORT_SCHEMA = {
    "analysis": "failure analysis summary",
    "probable_causes": ["likely causes"],
    "retry": "boolean",
    "args": {"corrected": "tool arguments when retry is true"},
    "corrections": ["proposed fixes or strategy changes"],
    "reason": "why this correction should work",
    "evidence": {
        "stack_trace": "stack trace excerpt if present",
        "error": "observed error text",
    },
}

DEBUGGER_PROMPT = """You are debugger_agent, the autonomous failure recovery specialist of Anubis.

Responsibilities:
- Analyze stack traces.
- Identify probable causes.
- Propose corrections.
- Rerun fixes automatically through corrected tool arguments.

Debugging rules:
- Stay autonomous and never ask humans for help.
- Turn every failure into either a concrete retry or a strategy change.
- Prefer root-cause fixes over surface patches.
- Preserve failing evidence in structured form.
- If retry is useful, return corrected args for the same tool.
- If retry is not useful, return retry=false and explain the strategy change.

Return JSON compatible with this schema:
{
  "analysis": "...",
  "probable_causes": ["..."],
  "retry": true,
  "args": {},
  "corrections": ["..."],
  "reason": "...",
  "evidence": {
    "stack_trace": "...",
    "error": "..."
  }
}"""


def create_debugger_state() -> dict[str, Any]:
    return {
        "agent": DEBUGGER_AGENT,
        "responsibilities": DEBUGGER_RESPONSIBILITIES,
        "rules": DEBUGGER_RULES,
        "report_schema": DEBUGGER_REPORT_SCHEMA,
        "status": "ready",
    }


def build_debugger_context(memory: dict[str, Any]) -> str:
    debugger_state = memory.get("debugger_agent")
    if not isinstance(debugger_state, dict):
        debugger_state = create_debugger_state()
        memory["debugger_agent"] = debugger_state

    return (
        "Debugger agent contract:\n"
        + "\n".join(f"- {item}" for item in DEBUGGER_RESPONSIBILITIES)
        + "\n\nDebugger rules:\n"
        + "\n".join(f"- {item}" for item in DEBUGGER_RULES)
        + "\n\nDebugger report schema:\n"
        + json.dumps(DEBUGGER_REPORT_SCHEMA, ensure_ascii=False, indent=2)
    )


def normalize_debugger_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "analysis": "Debugger output was not structured JSON",
            "probable_causes": ["unknown"],
            "retry": False,
            "args": {},
            "corrections": [],
            "reason": str(value),
            "evidence": {"stack_trace": "", "error": str(value)},
        }

    probable_causes = value.get("probable_causes", [])
    if not isinstance(probable_causes, list):
        probable_causes = [probable_causes]

    corrections = value.get("corrections", [])
    if not isinstance(corrections, list):
        corrections = [corrections]

    args = value.get("args", {})
    if not isinstance(args, dict):
        args = {}

    evidence = value.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {"stack_trace": "", "error": str(evidence)}

    return {
        "analysis": str(value.get("analysis", "")),
        "probable_causes": [str(item) for item in probable_causes if str(item).strip()],
        "retry": bool(value.get("retry", False)),
        "args": args,
        "corrections": [str(item) for item in corrections if str(item).strip()],
        "reason": str(value.get("reason", "")),
        "evidence": {
            "stack_trace": str(evidence.get("stack_trace", "")),
            "error": str(evidence.get("error", "")),
        },
    }


__all__ = [
    "DEBUGGER_AGENT",
    "DEBUGGER_PROMPT",
    "DEBUGGER_REPORT_SCHEMA",
    "DEBUGGER_RESPONSIBILITIES",
    "DEBUGGER_RULES",
    "build_debugger_context",
    "create_debugger_state",
    "normalize_debugger_report",
]
