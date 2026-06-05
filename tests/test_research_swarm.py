from anubis import EventType, build_runtime


async def test_research_hive_produces_traceable_consensus():
    runtime = await build_runtime()
    result = await runtime.research_hive.research("Map likely causes of local auth anomalies")

    assert result.consensus.decision == "accept"
    assert result.consensus.confidence > 0.5
    assert len(result.insights) == 5
    assert {insight.role.value for insight in result.insights} == {
        "planner",
        "executor",
        "analyst",
        "critic",
        "synthesizer",
    }
    assert len(result.reasoning_chain) == 5
    assert all("agent" in item and "summary" in item for item in result.reasoning_chain)
    assert len(result.consensus.votes) == 5
    assert EventType.SWARM_CONSENSUS_REACHED in [event.type for event in runtime.event_bus.events]


async def test_swarm_memory_is_shared_between_agents():
    runtime = await build_runtime()
    result = await runtime.research_hive.research("Summarize defensive posture")
    records = runtime.research_hive.memory.recall(result.session_id)

    assert len(records) == 5
    assert {record.metadata["role"] for record in records} == {
        "planner",
        "executor",
        "analyst",
        "critic",
        "synthesizer",
    }
