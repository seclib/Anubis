"""Lifecycle task scheduler adapter."""

from anubis.orchestrator import Orchestrator
from anubis.types import Task


class LifeScheduler:
    def __init__(self, orchestrator: Orchestrator) -> None:
        self.orchestrator = orchestrator

    async def schedule(self, task: Task) -> str:
        return await self.orchestrator.submit(task)

