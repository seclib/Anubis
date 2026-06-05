"""Critic agent: reviews structured outputs for risk and completeness."""

from __future__ import annotations

from core.agents.base_agent import AgentDescriptor, AgentInputError, BaseAgent, StructuredDict


class CriticAgent(BaseAgent):
    """Single-responsibility agent for deterministic output critique."""

    def __init__(self) -> None:
        super().__init__(
            descriptor=AgentDescriptor(
                name="critic_agent",
                role="critic",
                capabilities=frozenset({"critique.review", "risk.score"}),
                description="Reviews structured agent outputs for gaps and policy risk.",
            )
        )

    def handle(self, input_data: StructuredDict) -> StructuredDict:
        subject = self.optional_mapping(input_data, "subject")
        if not subject:
            raise AgentInputError("missing required dictionary field: subject")

        issues: list[StructuredDict] = []
        if subject.get("ok") is False:
            issues.append(
                {
                    "code": "upstream_agent_failed",
                    "severity": "high",
                    "message": "Subject output indicates failure.",
                }
            )
        if not subject.get("trace"):
            issues.append(
                {
                    "code": "missing_trace",
                    "severity": "medium",
                    "message": "Subject output lacks traceability metadata.",
                }
            )
        output = subject.get("output")
        if not isinstance(output, dict) or not output:
            issues.append(
                {
                    "code": "empty_output",
                    "severity": "medium",
                    "message": "Subject output is empty or not structured.",
                }
            )

        serialized = repr(subject).lower()
        if any(token in serialized for token in ("subprocess", " os.", "shell", "system access")):
            issues.append(
                {
                    "code": "unsafe_system_access_reference",
                    "severity": "critical",
                    "message": "Subject references direct system access concepts.",
                }
            )

        risk_score = self._score(issues)
        return {
            "decision": "revise" if risk_score >= 0.6 else "accept",
            "risk_score": risk_score,
            "issues": issues,
            "issue_count": len(issues),
            "explanation": "Critique uses deterministic checks on supplied structured data.",
        }

    @staticmethod
    def _score(issues: list[StructuredDict]) -> float:
        weights = {"low": 0.15, "medium": 0.3, "high": 0.55, "critical": 0.85}
        score = sum(weights.get(str(issue.get("severity")), 0.2) for issue in issues)
        return round(min(score, 1.0), 2)


__all__ = ["CriticAgent"]
