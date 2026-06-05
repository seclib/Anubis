"""Main cognitive cycle for turning stimuli into plans."""

from dataclasses import dataclass

from anubis.planner import Goal, Plan, PlanningEngine


@dataclass(slots=True)
class CognitiveLoop:
    planner: PlanningEngine

    async def think(self, goal: Goal) -> Plan:
        return await self.planner.create_plan(goal)

