from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class OsintInput:
    target: str
    context: str = ""


@dataclass
class IdentityReport:
    names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)


@dataclass
class FootprintReport:
    platforms: list[str] = field(default_factory=list)
    mentions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class AnalysisReport:
    confidence: float = 0.0
    inferred_traits: list[str] = field(default_factory=list)


@dataclass
class OsintReport:
    identity: IdentityReport = field(default_factory=IdentityReport)
    footprint: FootprintReport = field(default_factory=FootprintReport)
    analysis: AnalysisReport = field(default_factory=AnalysisReport)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterExecution:
    report: OsintReport
    diagnostics: list[str] = field(default_factory=list)


__all__ = [
    "AdapterExecution",
    "AnalysisReport",
    "FootprintReport",
    "IdentityReport",
    "OsintInput",
    "OsintReport",
]

