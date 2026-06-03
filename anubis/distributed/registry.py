"""Agent registry for distributed ANUBIS workers."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock

from anubis.distributed.contracts import AgentRegistration, AgentType


class AgentRegistry:
    """Tracks worker availability and capacity by agent type."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}
        self._lock = RLock()

    def register(self, registration: AgentRegistration) -> AgentRegistration:
        if registration.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        with self._lock:
            self._agents[registration.agent_id] = registration
        return registration

    def unregister(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def list_agents(self, agent_type: AgentType | None = None) -> tuple[AgentRegistration, ...]:
        with self._lock:
            agents = tuple(self._agents.values())
        if agent_type is None:
            return agents
        return tuple(agent for agent in agents if agent.agent_type == agent_type)

    def available(self, agent_type: AgentType) -> tuple[AgentRegistration, ...]:
        return tuple(
            agent
            for agent in self.list_agents(agent_type)
            if agent.enabled and agent.available_capacity > 0
        )

    def acquire(self, agent_id: str) -> AgentRegistration:
        with self._lock:
            registration = self._agents.get(agent_id)
            if registration is None:
                raise KeyError(f"Unknown agent: {agent_id}")
            if not registration.enabled or registration.available_capacity < 1:
                raise RuntimeError(f"Agent has no available capacity: {agent_id}")
            updated = replace(
                registration,
                active_assignments=registration.active_assignments + 1,
            )
            self._agents[agent_id] = updated
            return updated

    def release(self, agent_id: str) -> AgentRegistration | None:
        with self._lock:
            registration = self._agents.get(agent_id)
            if registration is None:
                return None
            updated = replace(
                registration,
                active_assignments=max(0, registration.active_assignments - 1),
            )
            self._agents[agent_id] = updated
            return updated

    def set_enabled(self, agent_id: str, enabled: bool) -> AgentRegistration:
        with self._lock:
            registration = self._agents.get(agent_id)
            if registration is None:
                raise KeyError(f"Unknown agent: {agent_id}")
            updated = replace(registration, enabled=enabled)
            self._agents[agent_id] = updated
            return updated


__all__ = ["AgentRegistry"]
