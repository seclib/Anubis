from __future__ import annotations

from dataclasses import dataclass

from anubis_cli_mvp.agents import AgentManager
from anubis_cli_mvp.memory import MemoryStore
from anubis_cli_mvp.renderer import Renderer
from anubis_cli_mvp.swarm import SwarmEngine


@dataclass
class CommandContext:
    renderer: Renderer
    agents: AgentManager
    memory: MemoryStore
    swarm: SwarmEngine
    running: bool = True
