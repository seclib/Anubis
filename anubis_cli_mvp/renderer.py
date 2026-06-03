from __future__ import annotations

import time

from anubis_cli_mvp.models import RenderBlock


AGENT_DISPLAY_ORDER = ("builder", "researcher", "analyst", "orchestrator")


class Renderer:
    """Strict structured terminal renderer."""

    def line(self, text: str = "") -> None:
        print(text)

    def boot(self, delay: float) -> None:
        for stage in (
            "Core loading",
            "Hermes engine loading",
            "Memory system loading",
            "Agent runtime loading",
            "System ready",
        ):
            self.line(stage)
            if delay > 0:
                time.sleep(delay)
        self.line()

    def block(self, block: RenderBlock) -> None:
        self.line("TASK:")
        self.line(block.task)
        self.line()
        self.line("STATUS:")
        self._status(block.status)
        self.line()
        self.line("RESULT:")
        self.line(block.result)
        self.line()

    def _status(self, status: dict[str, str] | None) -> None:
        if not status:
            self.line("none")
            return

        emitted = set()
        for name in AGENT_DISPLAY_ORDER:
            if name in status:
                self.line(f"{name}: {status[name]}")
                emitted.add(name)

        for name in sorted(set(status) - emitted):
            self.line(f"{name}: {status[name]}")
