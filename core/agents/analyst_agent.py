"""Analyst agent: interprets structured observations without side effects."""

from __future__ import annotations

from typing import Any, Mapping

from core.agents.base_agent import AgentDescriptor, AgentInputError, BaseAgent, StructuredDict


class AnalystAgent(BaseAgent):
    """Single-responsibility agent for evidence interpretation."""

    def __init__(self) -> None:
        super().__init__(
            descriptor=AgentDescriptor(
                name="analyst_agent",
                role="analyst",
                capabilities=frozenset({"analysis.interpret", "analysis.summarize"}),
                description="Interprets supplied observations and produces findings.",
            )
        )

    def handle(self, input_data: StructuredDict) -> StructuredDict:
        objective = self.require_string(input_data, "objective")
        observations = input_data.get("observations", [])
        normalized = self._normalize_observations(observations)

        suspicious = [
            item
            for item in normalized
            if any(token in item["text"].lower() for token in ("fail", "deny", "anomal", "risk"))
        ]
        confidence = 0.5 + min(len(normalized), 5) * 0.06 + min(len(suspicious), 3) * 0.07
        confidence = round(min(confidence, 0.95), 2)

        finding = (
            "suspicious_patterns_detected"
            if suspicious
            else "no_suspicious_pattern_in_supplied_observations"
        )
        return {
            "objective": objective,
            "finding": finding,
            "confidence": confidence,
            "observation_count": len(normalized),
            "signals": normalized,
            "evidence_ids": [item["id"] for item in suspicious],
            "explanation": (
                "Analysis is based only on caller-supplied structured observations."
            ),
        }

    def _normalize_observations(self, observations: Any) -> list[StructuredDict]:
        if observations is None:
            return []
        if isinstance(observations, Mapping):
            observations = [observations]
        if not isinstance(observations, list):
            raise AgentInputError("observations must be a list of dictionaries or strings")

        normalized: list[StructuredDict] = []
        for index, item in enumerate(observations):
            if isinstance(item, Mapping):
                text = str(item.get("text") or item.get("summary") or item)
                identifier = str(item.get("id") or f"observation_{index + 1}")
                severity = str(item.get("severity") or "unknown")
            else:
                text = str(item)
                identifier = f"observation_{index + 1}"
                severity = "unknown"
            normalized.append({"id": identifier, "text": text, "severity": severity})
        return normalized


__all__ = ["AnalystAgent"]
