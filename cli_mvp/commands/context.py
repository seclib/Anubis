from __future__ import annotations

from dataclasses import dataclass

from cli_mvp.agents import AgentManager
from cli_mvp.memory import MemoryStore
from cli_mvp.renderer import Renderer
from cli_mvp.swarm import SwarmEngine


@dataclass
class CommandContext:
    renderer: Renderer
    agents: AgentManager
    memory: MemoryStore
    swarm: SwarmEngine
    running: bool = True
