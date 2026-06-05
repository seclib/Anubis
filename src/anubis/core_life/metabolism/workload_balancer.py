"""Simple workload balancing helpers."""

from anubis.agents import AgentRuntime


class WorkloadBalancer:
    def choose(self, agents: tuple[AgentRuntime, ...]) -> AgentRuntime | None:
        if not agents:
            return None
        return sorted(agents, key=lambda agent: (-agent.available_capacity, agent.descriptor.name))[0]

