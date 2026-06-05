from __future__ import annotations

from io import StringIO

from core.bootstrap import DEFAULT_STIMULUS, BootstrapConfig, collect_stimuli, run_bootstrap


class TtyInput(StringIO):
    def isatty(self) -> bool:
        return True


class PipeInput(StringIO):
    def isatty(self) -> bool:
        return False


def test_collect_stimuli_prefers_cli_arguments() -> None:
    config = collect_stimuli(
        ["Investigate", "sandbox", "denial", "--source", "cli"],
        PipeInput("ignored stdin"),
    )

    assert config.stimuli == ("Investigate sandbox denial",)
    assert config.source == "cli"


def test_collect_stimuli_reads_non_interactive_stdin() -> None:
    config = collect_stimuli([], PipeInput("First stimulus\n\nSecond stimulus\n"))

    assert config.stimuli == ("First stimulus", "Second stimulus")
    assert config.source == "operator"


def test_collect_stimuli_uses_deterministic_default_for_tty() -> None:
    config = collect_stimuli([], TtyInput(""))

    assert config.stimuli == (DEFAULT_STIMULUS,)


async def test_run_bootstrap_routes_input_through_full_pipeline() -> None:
    result = await run_bootstrap(
        BootstrapConfig(
            stimuli=("Investigate test anomaly",),
            source="test",
            evolution_enabled=False,
        )
    )
    payload = result.to_dict()

    assert payload["system"] == "ANUBIS"
    assert payload["status"] == "completed"
    assert payload["request_count"] == 1
    assert payload["modules"] == (
        "orchestrator",
        "planner",
        "agents",
        "execution",
        "memory",
        "security",
        "plugins",
        "observability",
    )
    assert payload["results"][0]["status"] == "succeeded"
    assert payload["results"][0]["goal"] == "Investigate test anomaly"
    assert payload["results"][0]["task_ids"]
