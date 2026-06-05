from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anubis.ui.event_stream import Event, EventBus


@dataclass
class AgentLiveState:
    agent: str
    task: str = ""
    status: str = "idle"
    progress: int = 0


@dataclass
class SwarmLiveState:
    goal: str = ""
    active_agents: dict[str, AgentLiveState] = field(default_factory=dict)
    running_tasks: dict[str, str] = field(default_factory=dict)
    completed: bool = False


class StateBridge:
    def __init__(self, bus: EventBus | None = None) -> None:
        self.state = SwarmLiveState()
        if bus is not None:
            bus.subscribe(self.handle)

    def handle(self, event: Event) -> None:
        payload = event.payload
        if event.type == "swarm_started":
            self.state.goal = str(payload.get("goal", ""))
            self.state.completed = False
            return

        if event.type == "swarm_completed":
            self.state.completed = True
            for agent in self.state.active_agents.values():
                agent.progress = 100
                agent.status = "completed"
            self.state.running_tasks.clear()
            return

        agent_name = str(payload.get("agent", "")).strip()
        if not agent_name:
            return

        agent = self.state.active_agents.setdefault(agent_name, AgentLiveState(agent=agent_name))
        if "task" in payload:
            agent.task = str(payload.get("task", ""))

        if event.type == "agent_started":
            agent.status = "running"
            agent.progress = int(payload.get("progress", 0))
            self.state.running_tasks[agent_name] = agent.task
        elif event.type == "agent_progress":
            agent.status = "running"
            agent.progress = _clamp_progress(payload.get("progress", agent.progress))
            self.state.running_tasks[agent_name] = agent.task
        elif event.type == "agent_completed":
            agent.status = "completed"
            agent.progress = 100
            self.state.running_tasks.pop(agent_name, None)

    def snapshot(self) -> dict[str, Any]:
        return {
            "goal": self.state.goal,
            "completed": self.state.completed,
            "active_agents": {
                name: {
                    "task": item.task,
                    "status": item.status,
                    "progress": item.progress,
                }
                for name, item in sorted(self.state.active_agents.items())
            },
            "running_tasks": dict(sorted(self.state.running_tasks.items())),
        }


def _clamp_progress(value: Any) -> int:
    try:
        progress = int(value)
    except (TypeError, ValueError):
        progress = 0
    return max(0, min(100, progress))


__all__ = ["AgentLiveState", "StateBridge", "SwarmLiveState"]
