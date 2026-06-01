from __future__ import annotations

import re

from anubis_rag.security.models import RiskType, SecurityFilterResult


class SecurityFilter:
    PATTERNS: tuple[tuple[str, RiskType, re.Pattern[str]], ...] = (
        ("ignore_previous_instructions", "prompt_injection", re.compile(r"\bignore\s+(all\s+)?(previous|prior)\s+instructions\b", re.I)),
        ("ignore_system", "prompt_injection", re.compile(r"\bignore\s+(the\s+)?system\b", re.I)),
        ("you_are_now", "system_override", re.compile(r"\byou\s+are\s+now\b", re.I)),
        ("act_as", "system_override", re.compile(r"\bact\s+as\b", re.I)),
        ("system_prompt", "system_override", re.compile(r"\bsystem\s+prompt\b", re.I)),
        ("execute", "tool_manipulation", re.compile(r"\bexecute\b", re.I)),
        ("call_tool", "tool_manipulation", re.compile(r"\bcall\s+(the\s+)?tool\b", re.I)),
        ("delete_files", "tool_manipulation", re.compile(r"\bdelete\s+(all\s+)?files\b", re.I)),
        ("override", "prompt_injection", re.compile(r"\boverride\b", re.I)),
        ("tool_json", "tool_manipulation", re.compile(r"\"tool_name\"\s*:", re.I)),
        ("memory_poisoning", "data_poisoning", re.compile(r"\b(store|save|remember)\s+this\s+(as\s+)?(permanent\s+)?memory\b", re.I)),
    )

    def inspect(self, text: str) -> SecurityFilterResult:
        detected: list[str] = []
        risk_type: RiskType = "benign"
        for name, candidate_risk, pattern in self.PATTERNS:
            if pattern.search(text):
                detected.append(name)
                if risk_type == "benign" or candidate_risk in {"tool_manipulation", "system_override"}:
                    risk_type = candidate_risk

        if not detected:
            return SecurityFilterResult(safe=True, reason="No adversarial patterns detected.", risk_type="benign")

        return SecurityFilterResult(
            safe=False,
            reason="Instruction-like or adversarial content detected; chunk downgraded to low-trust data only.",
            risk_type=risk_type,
            detected_patterns=detected,
        )
