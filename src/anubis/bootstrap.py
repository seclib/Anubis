"""Birth point for the ANUBIS system."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from anubis.api_body.stimulus_input import StimulusInput
from anubis.life_cycle.boot_sequence import build_runtime


async def run_demo() -> None:
    runtime = await build_runtime(evolution_enabled=True)
    stimuli = (
        StimulusInput("Investigate anomalous authentication activity", source="demo.sensor"),
        StimulusInput("Review local sandbox posture after failed plugin attempt", source="demo.operator"),
    )

    print("ANUBIS online")
    print("agents:", ", ".join(agent.name for agent in runtime.agents))

    for stimulus in stimuli:
        result = await runtime.cognitive_loop.run(stimulus)
        swarm_result = await runtime.research_hive.research(stimulus.text)
        print("\ncycle:", stimulus.text)
        print(
            json.dumps(
                {
                    "goal": result.goal.objective,
                    "plan_status": result.plan.status.value if result.plan else None,
                    "steps": [
                        {
                            "task_id": step_result.task_id,
                            "status": step_result.status.value,
                            "output": dict(step_result.output),
                            "error": step_result.error,
                        }
                        for step_result in result.step_results
                    ],
                    "final_status": result.task_result.status.value,
                    "reflection": {
                        "event_count": result.reflection.event_count,
                        "findings": [
                            {
                                "signal": finding.signal.value,
                                "score": finding.score,
                                "message": finding.message,
                            }
                            for finding in result.reflection.findings
                        ],
                    },
                    "evolution": {
                        "enabled": result.evolution.enabled if result.evolution else False,
                        "fitness": (
                            result.evolution.fitness.as_dict() if result.evolution else None
                        ),
                        "proposals": len(result.upgrade_proposals),
                        "simulations": (
                            len(result.evolution.simulations) if result.evolution else 0
                        ),
                        "genome_versions": (
                            [version.id for version in result.evolution.genome_versions]
                            if result.evolution
                            else []
                        ),
                        "patch_diffs": (
                            [
                                version.diff
                                for version in result.evolution.genome_versions[:2]
                            ]
                            if result.evolution
                            else []
                        ),
                        "review_required": True,
                        "patch_results": len(result.patch_results),
                    },
                    "memory": result.memory_write.explanation,
                    "research_swarm": {
                        "session_id": swarm_result.session_id,
                        "allocations": [
                            {
                                "role": allocation.role.value,
                                "agent": allocation.agent_name,
                                "score": allocation.score,
                                "reason": allocation.reason,
                            }
                            for allocation in swarm_result.allocations
                        ],
                        "reasoning_chain": [dict(item) for item in swarm_result.reasoning_chain],
                        "consensus": {
                            "decision": swarm_result.consensus.decision,
                            "confidence": swarm_result.consensus.confidence,
                            "votes": [
                                {
                                    "agent": vote.agent_name,
                                    "role": vote.role.value,
                                    "decision": vote.decision,
                                    "confidence": vote.confidence,
                                    "weight": vote.weight,
                                }
                                for vote in swarm_result.consensus.votes
                            ],
                            "conflicts": swarm_result.consensus.conflicts,
                            "explanation": swarm_result.consensus.explanation,
                        },
                    },
                },
                indent=2,
                sort_keys=True,
                default=_json_default,
            )
        )

    print("\nrecent_memory:")
    for record in runtime.episodic_memory.recent(limit=5):
        print("-", record.content)

    print("\nevent_trace:")
    for record in runtime.logger.records:
        print(
            json.dumps(
                {
                    "level": record.level,
                    "component": record.component,
                    "message": record.message,
                    "task_id": record.metadata.get("task_id"),
                    "agent_name": record.metadata.get("agent_name"),
                },
                sort_keys=True,
                default=_json_default,
            )
        )


def main() -> None:
    asyncio.run(run_demo())


def _json_default(value: Any) -> str:
    return str(value)


if __name__ == "__main__":
    main()
