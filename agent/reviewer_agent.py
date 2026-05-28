"""Dedicated reviewer agent contract and code review helpers."""

from __future__ import annotations

import json
from typing import Any

REVIEWER_AGENT = "reviewer_agent"

REVIEWER_RESPONSIBILITIES = [
    "review_generated_code",
    "detect_potential_bugs",
    "verify_architecture_quality",
    "propose_improvements",
]

REVIEWER_RULES = [
    "act as a critical senior engineer",
    "prioritize correctness, regressions, security, and maintainability",
    "ground findings in available evidence",
    "avoid style-only feedback unless it affects quality",
    "do not approve incomplete work",
]

REVIEW_REPORT_SCHEMA = {
    "success": "boolean",
    "status": "approved | changes_requested | needs_more_evidence",
    "summary": "short review summary",
    "findings": [
        {
            "severity": "critical | high | medium | low",
            "message": "bug, architecture issue, or quality concern",
            "evidence": "file, tool output, or observed behavior",
            "recommendation": "specific improvement",
        }
    ],
    "architecture_notes": ["architecture quality observations"],
    "improvements": ["recommended improvements"],
    "reason": "completion decision rationale",
}

REVIEWER_PROMPT = """You are reviewer_agent, a critical senior engineer reviewing generated work.

Responsibilities:
- Review generated code.
- Detect potential bugs.
- Verify architecture quality.
- Propose improvements.

Review rules:
- Act as a critical senior engineer.
- Prioritize correctness, regressions, security, and maintainability.
- Ground findings in available evidence.
- Avoid style-only feedback unless it affects quality.
- Do not approve incomplete work.
- Do not ask humans for help.

Return JSON compatible with this schema:
{
  "success": true,
  "status": "approved | changes_requested | needs_more_evidence",
  "summary": "...",
  "findings": [
    {
      "severity": "critical | high | medium | low",
      "message": "...",
      "evidence": "...",
      "recommendation": "..."
    }
  ],
  "architecture_notes": ["..."],
  "improvements": ["..."],
  "reason": "..."
}"""


def create_reviewer_state() -> dict[str, Any]:
    return {
        "agent": REVIEWER_AGENT,
        "responsibilities": REVIEWER_RESPONSIBILITIES,
        "rules": REVIEWER_RULES,
        "report_schema": REVIEW_REPORT_SCHEMA,
        "status": "ready",
    }


def build_reviewer_context(memory: dict[str, Any]) -> str:
    reviewer_state = memory.get("reviewer_agent")
    if not isinstance(reviewer_state, dict):
        reviewer_state = create_reviewer_state()
        memory["reviewer_agent"] = reviewer_state

    return (
        "Reviewer agent contract:\n"
        + "\n".join(f"- {item}" for item in REVIEWER_RESPONSIBILITIES)
        + "\n\nReviewer rules:\n"
        + "\n".join(f"- {item}" for item in REVIEWER_RULES)
        + "\n\nReview report schema:\n"
        + json.dumps(REVIEW_REPORT_SCHEMA, ensure_ascii=False, indent=2)
    )


def normalize_review_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "success": False,
            "status": "needs_more_evidence",
            "summary": "Reviewer output was not structured JSON",
            "findings": [
                {
                    "severity": "medium",
                    "message": str(value),
                    "evidence": "",
                    "recommendation": "Retry review with structured output",
                }
            ],
            "architecture_notes": [],
            "improvements": [],
            "reason": str(value),
        }

    findings = value.get("findings", [])
    if not isinstance(findings, list):
        findings = [findings]

    architecture_notes = value.get("architecture_notes", [])
    if not isinstance(architecture_notes, list):
        architecture_notes = [architecture_notes]

    improvements = value.get("improvements", [])
    if not isinstance(improvements, list):
        improvements = [improvements]

    status = str(value.get("status", "approved" if value.get("success") else "changes_requested"))
    if status not in {"approved", "changes_requested", "needs_more_evidence"}:
        status = "needs_more_evidence"

    return {
        "success": bool(value.get("success", status == "approved")),
        "status": status,
        "summary": str(value.get("summary", "")),
        "findings": [
            finding
            if isinstance(finding, dict)
            else {
                "severity": "medium",
                "message": str(finding),
                "evidence": "",
                "recommendation": "",
            }
            for finding in findings
        ],
        "architecture_notes": [str(item) for item in architecture_notes if str(item).strip()],
        "improvements": [str(item) for item in improvements if str(item).strip()],
        "reason": str(value.get("reason", value.get("summary", ""))),
    }


__all__ = [
    "REVIEWER_AGENT",
    "REVIEWER_PROMPT",
    "REVIEWER_RESPONSIBILITIES",
    "REVIEWER_RULES",
    "REVIEW_REPORT_SCHEMA",
    "build_reviewer_context",
    "create_reviewer_state",
    "normalize_review_report",
]
