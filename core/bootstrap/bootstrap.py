"""Deterministic bootstrap entrypoint for ANUBIS."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any, Iterable, TextIO

from core.graph import GraphExecutionResult, GraphOrchestrator


DEFAULT_STIMULUS = "Investigate local authentication anomaly"


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    stimuli: tuple[str, ...] = (DEFAULT_STIMULUS,)
    source: str = "operator"
    evolution_enabled: bool = False

    def __post_init__(self) -> None:
        stimuli = tuple(stimulus.strip() for stimulus in self.stimuli if stimulus.strip())
        if not stimuli:
            stimuli = (DEFAULT_STIMULUS,)
        object.__setattr__(self, "stimuli", stimuli)
        object.__setattr__(self, "source", self.source.strip() or "operator")


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    modules: tuple[str, ...]
    results: tuple[GraphExecutionResult, ...]
    request_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": "ANUBIS",
            "status": "completed",
            "modules": self.modules,
            "request_count": self.request_count,
            "results": [result.to_dict() for result in self.results],
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start ANUBIS deterministic bootstrap.")
    parser.add_argument(
        "stimulus",
        nargs="*",
        help="User input to route through ANUBIS. If omitted, stdin or a deterministic sample is used.",
    )
    parser.add_argument("--source", default="operator", help="Source label for the stimulus.")
    parser.add_argument(
        "--evolution",
        action="store_true",
        help="Enable review-only evolution simulation during runtime startup.",
    )
    return parser


def collect_stimuli(argv: Iterable[str], stdin: TextIO) -> BootstrapConfig:
    args = build_arg_parser().parse_args(tuple(argv))
    if args.stimulus:
        stimuli = (" ".join(args.stimulus),)
    elif not stdin.isatty():
        stimuli = tuple(line.strip() for line in stdin.read().splitlines() if line.strip())
    else:
        stimuli = (DEFAULT_STIMULUS,)
    return BootstrapConfig(
        stimuli=stimuli,
        source=args.source,
        evolution_enabled=args.evolution,
    )


async def run_bootstrap(config: BootstrapConfig) -> BootstrapResult:
    orchestrator = GraphOrchestrator.build()
    results: list[GraphExecutionResult] = []
    for index, stimulus in enumerate(config.stimuli, start=1):
        result = orchestrator.run_once(
            stimulus,
            source=config.source,
            context={"bootstrap_sequence": index},
        )
        results.append(result)
    return BootstrapResult(
        modules=(
            "orchestrator",
            "planner",
            "agents",
            "execution",
            "memory",
            "security",
            "plugins",
            "observability",
        ),
        results=tuple(results),
        request_count=orchestrator.run_count,
    )


async def async_main(argv: Iterable[str] | None = None, stdin: TextIO | None = None) -> BootstrapResult:
    config = collect_stimuli(sys.argv[1:] if argv is None else argv, stdin or sys.stdin)
    result = await run_bootstrap(config)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
    return result


def main(argv: Iterable[str] | None = None) -> None:
    asyncio.run(async_main(argv=argv))


__all__ = [
    "BootstrapConfig",
    "BootstrapResult",
    "DEFAULT_STIMULUS",
    "async_main",
    "collect_stimuli",
    "main",
    "run_bootstrap",
]
