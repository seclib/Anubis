from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from anubis.api_body.stimulus_input import StimulusInput
from anubis.core_life.brain.intent_inference import IntentInference
from anubis.core_life.brain.reflection_engine import ReflectionEngine
from anubis.core_life.evolution.self_refactor_engine import EvolutionCycleResult, EvolutionEngine
from anubis.core_life.memory_life.episodic_memory import EpisodicMemory
from anubis.core_life.metabolism.task_digestion import TaskDigestion
from anubis.events import EventBus
from anubis.memory import ConflictResolution
from anubis.orchestrator import Orchestrator
from anubis.planner import Goal, Plan, PlanStatus, PlanningEngine, default_security_templates
from anubis.self_improvement import (
    PatchGenerationEngine,
    PatchGenerationResult,
    PerformanceAnalyzer,
    PerformanceReport,
    UpgradePlanner,
    UpgradeProposal,
)
from anubis.swarm import PerformanceOutcome, SwarmCoordinator, SwarmSession
from anubis.types import Event, EventType, Task, TaskResult, TaskStatus


@dataclass(frozen=True, slots=True)
class LivingLoopResult:
    stimulus: StimulusInput
    goal: Goal
    plan: Plan | None
    task: Task
    swarm_session: SwarmSession
    task_result: TaskResult
    memory_write: ConflictResolution
    reflection: PerformanceReport
    step_results: tuple[TaskResult, ...] = field(default_factory=tuple)
    evolution: EvolutionCycleResult | None = None
    upgrade_proposals: tuple[UpgradeProposal, ...] = field(default_factory=tuple)
    patch_results: tuple[PatchGenerationResult, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.task_result.status == TaskStatus.SUCCEEDED


class PrincipalLoop:
    """Main ANUBIS life loop from stimulus to reflection."""

    def __init__(
        self,
        *,
        intent_inference: IntentInference | None = None,
        task_digestion: TaskDigestion | None = None,
        hive_mind: SwarmCoordinator | None = None,
        orchestrator: Orchestrator | None = None,
        planning_engine: PlanningEngine | None = None,
        episodic_memory: EpisodicMemory | None = None,
        self_refactor_engine: PatchGenerationEngine | None = None,
        evolution_engine: EvolutionEngine | None = None,
        reflection_engine: ReflectionEngine | None = None,
        upgrade_planner: UpgradePlanner | None = None,
        event_bus: EventBus | None = None,
        evolution_paths: Sequence[str | Path] = (),
        owner_id: str = "principal_loop",
    ) -> None:
        self.intent_inference = intent_inference or IntentInference()
        self.task_digestion = task_digestion or TaskDigestion()
        self.orchestrator = orchestrator or Orchestrator(event_bus=event_bus)
        self.event_bus = event_bus or self.orchestrator.event_bus
        self.planning_engine = planning_engine or PlanningEngine(
            templates=default_security_templates(),
            agent_registry=self.orchestrator.agent_registry,
        )
        self.hive_mind = hive_mind or SwarmCoordinator(
            agent_registry=self.orchestrator.agent_registry
        )
        self.episodic_memory = episodic_memory or EpisodicMemory()
        self.self_refactor_engine = self_refactor_engine or PatchGenerationEngine(
            event_bus=self.event_bus
        )
        self.evolution_engine = evolution_engine
        self.reflection_engine = reflection_engine or ReflectionEngine(
            PerformanceAnalyzer(event_bus=self.event_bus)
        )
        self.upgrade_planner = upgrade_planner or UpgradePlanner(event_bus=self.event_bus)
        self.evolution_paths = tuple(Path(path) for path in evolution_paths)
        self.owner_id = owner_id

    async def run(
        self,
        stimulus: StimulusInput | str,
        *,
        kind: str = "investigate_alert",
        context: Mapping[str, Any] | None = None,
    ) -> LivingLoopResult:
        normalized = self._normalize_stimulus(stimulus)
        await self._publish(
            EventType.LIFE_LOOP_STARTED,
            {
                "source": normalized.source,
                "text": normalized.text,
                "kind": kind,
            },
        )

        try:
            goal = self.intent_inference.infer_goal(normalized.text, kind=kind)
            swarm_session = await self.hive_mind.create_session(
                goal.objective,
                metadata={
                    "stimulus_source": normalized.source,
                    **dict(context or {}),
                },
            )

            plan = await self.planning_engine.create_plan(goal)
            plan, task, task_result, step_results = await self._execute_plan(plan)
            self._score_swarm_agents(swarm_session, task_result)

            memory_write = self.episodic_memory.put(
                self.episodic_memory.episode(
                    self._episode_content(normalized, goal, task_result, plan, step_results),
                    scope_id=task.id,
                    owner_id=self.owner_id,
                ),
                actor_id=self.owner_id,
            )

            events_before_reflection = await self._events()
            reflection = await self.reflection_engine.reflect(events_before_reflection)
            evolution = await self._evolve(events_before_reflection)
            if evolution is None:
                upgrade_proposals = await self._propose_upgrades(reflection)
                patch_results = await self._generate_patch_results(upgrade_proposals)
            else:
                upgrade_proposals = (
                    evolution.mutation_plan.proposals
                    if evolution.mutation_plan is not None
                    else ()
                )
                patch_results = ()

            result = LivingLoopResult(
                stimulus=normalized,
                goal=goal,
                plan=plan,
                task=task,
                swarm_session=swarm_session,
                task_result=task_result,
                step_results=step_results,
                memory_write=memory_write,
                reflection=reflection,
                evolution=evolution,
                upgrade_proposals=upgrade_proposals,
                patch_results=patch_results,
            )
            await self._publish(
                EventType.LIFE_LOOP_COMPLETED,
                {
                    "stimulus_source": normalized.source,
                    "goal": goal.objective,
                    "task_id": task.id,
                    "task_status": task_result.status.value,
                    "memory_status": memory_write.status.value,
                    "upgrade_proposals": len(upgrade_proposals),
                    "patch_results": len(patch_results),
                },
                task_id=task.id,
            )
            return result
        except Exception as exc:
            await self._publish(
                EventType.LIFE_LOOP_FAILED,
                {
                    "source": normalized.source,
                    "text": normalized.text,
                    "error": str(exc),
                },
            )
            raise

    def _normalize_stimulus(self, stimulus: StimulusInput | str) -> StimulusInput:
        if isinstance(stimulus, StimulusInput):
            return stimulus
        return StimulusInput(text=stimulus)

    async def _execute_plan(
        self,
        plan: Plan,
    ) -> tuple[Plan, Task, TaskResult, tuple[TaskResult, ...]]:
        current = plan
        results: list[TaskResult] = []
        dispatched_task_ids: set[str] = set()

        while current.status not in {PlanStatus.SUCCEEDED, PlanStatus.FAILED}:
            before = {step.task_id for step in current.steps if step.task_id}
            current = await self.planning_engine.dispatch_ready(current, self.orchestrator)
            after = {step.task_id for step in current.steps if step.task_id}
            new_task_ids = tuple(sorted((after - before) - dispatched_task_ids))

            if not new_task_ids:
                break

            for task_id in new_task_ids:
                dispatched_task_ids.add(task_id)
                task_result = await self.orchestrator.wait(task_id)
                results.append(task_result)
                current = self.planning_engine.apply_result(current, task_result)

        if not results:
            task = self.task_digestion.digest_goal(plan.goal)
            result = TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error="plan produced no dispatchable tasks",
                output={"plan_id": plan.id, "plan_status": current.status.value},
            )
            return current, task, result, (result,)

        final_result = results[-1]
        final_record = await self.orchestrator.task_state(final_result.task_id)
        return current, final_record.task, final_result, tuple(results)

    async def _propose_upgrades(
        self,
        reflection: PerformanceReport,
    ) -> tuple[UpgradeProposal, ...]:
        if not self.evolution_paths:
            return ()
        return await self.upgrade_planner.propose_upgrades(
            performance_report=reflection,
            paths=self.evolution_paths,
        )

    async def _evolve(self, events: Sequence[Event]) -> EvolutionCycleResult | None:
        if self.evolution_engine is None:
            return None
        return await self.evolution_engine.evolve(
            events=events,
            paths=self.evolution_paths,
            memory_records=self.episodic_memory.recent(limit=50),
        )

    async def _generate_patch_results(
        self,
        proposals: Sequence[UpgradeProposal],
    ) -> tuple[PatchGenerationResult, ...]:
        results = []
        for proposal in proposals:
            results.append(await self.self_refactor_engine.apply_safe(proposal, root=Path(".")))
        return tuple(results)

    async def _events(self) -> tuple[Event, ...]:
        stored = await self.event_bus.replay()
        return tuple(item.event for item in stored)

    async def _publish(
        self,
        event_type: EventType,
        payload: Mapping[str, Any],
        *,
        task_id: str | None = None,
    ) -> None:
        await self.event_bus.publish(
            Event(
                type=event_type,
                producer="principal_loop",
                payload=payload,
                task_id=task_id,
            )
        )

    def _score_swarm_agents(
        self,
        session: SwarmSession,
        task_result: TaskResult,
    ) -> None:
        outcome = (
            PerformanceOutcome.SUCCESS
            if task_result.status == TaskStatus.SUCCEEDED
            else PerformanceOutcome.FAILURE
        )
        for agent_name in {assignment.agent_name for assignment in session.assignments}:
            self.hive_mind.update_performance(
                agent_name,
                outcome,
                reason=f"Principal loop task {task_result.task_id} ended as {task_result.status}.",
            )

    def _episode_content(
        self,
        stimulus: StimulusInput,
        goal: Goal,
        task_result: TaskResult,
        plan: Plan | None,
        step_results: Sequence[TaskResult],
    ) -> str:
        status = task_result.status.value
        plan_bits = ""
        if plan is not None:
            plan_bits = (
                f"; plan={plan.id}; steps={len(plan.steps)}; "
                f"step_results={[result.status.value for result in step_results]}"
            )
        if task_result.error:
            return (
                f"Stimulus from {stimulus.source}: {stimulus.text}; "
                f"goal={goal.objective}{plan_bits}; result={status}; error={task_result.error}"
            )
        return (
            f"Stimulus from {stimulus.source}: {stimulus.text}; "
            f"goal={goal.objective}{plan_bits}; result={status}; output={dict(task_result.output)}"
        )


LivingLoop = PrincipalLoop
