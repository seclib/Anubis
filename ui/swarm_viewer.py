from __future__ import annotations

from anubis.ui.event_stream import Event, EventBus
from anubis.ui.state_bridge import StateBridge


class SwarmViewer:
    def __init__(self, bridge: StateBridge) -> None:
        self.bridge = bridge

    def render(self) -> str:
        snapshot = self.bridge.snapshot()
        agents = snapshot["active_agents"]
        lines = ["SWARM LIVE:", ""]
        if not agents:
            lines.append("no active agents")
            return "\n".join(lines)

        for name in sorted(agents):
            progress = int(agents[name]["progress"])
            lines.append(f"{name:<11} {_bar(progress)} {progress}%")
        return "\n".join(lines)

    def print(self) -> None:
        print(self.render())


class LiveSwarmPrinter:
    def __init__(self, bus: EventBus) -> None:
        self.bridge = StateBridge(bus)
        self.viewer = SwarmViewer(self.bridge)
        bus.subscribe(self.handle)

    def handle(self, _event: Event) -> None:
        print(self.viewer.render())
        print()


def _bar(progress: int, width: int = 10) -> str:
    filled = max(0, min(width, round(width * progress / 100)))
    return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"


__all__ = ["LiveSwarmPrinter", "SwarmViewer"]
