from anubis import EventType, StimulusInput, build_runtime


async def test_build_runtime_executes_full_local_cycle():
    runtime = await build_runtime()
    result = await runtime.cognitive_loop.run(
        StimulusInput("Investigate a local anomaly", source="test")
    )

    assert result.succeeded
    assert result.plan is not None
    assert result.plan.status == "succeeded"
    assert len(result.step_results) == 3
    assert runtime.episodic_memory.recent(limit=1)[0].content.startswith("Stimulus from test")
    assert runtime.semantic_memory.recall("local-first")
    assert EventType.LIFE_LOOP_COMPLETED in [event.type for event in runtime.event_bus.events]
