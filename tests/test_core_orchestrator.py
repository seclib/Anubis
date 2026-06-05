from core.orchestrator import Orchestrator, RequestStatus


async def test_production_orchestrator_handles_user_input_with_structured_logs():
    orchestrator = await Orchestrator.create()

    result = await orchestrator.receive_user_input(
        "Investigate local authentication anomaly",
        source="test",
    )

    assert result.status == RequestStatus.SUCCEEDED
    assert result.goal == "Investigate local authentication anomaly"
    assert result.plan_id is not None
    assert result.task_ids
    assert result.memory_record_id is not None
    assert result.event_count > 0
    assert [record.status for record in orchestrator.request_state] == [RequestStatus.SUCCEEDED]
    assert [log["action"] for log in result.logs] == [
        "input.accepted",
        "state.planned",
        "state.running",
        "execution.completed",
    ]


async def test_production_orchestrator_returns_structured_error_for_empty_input():
    orchestrator = await Orchestrator.create()

    result = await orchestrator.handle_input("   ", source="test")

    assert result.status == RequestStatus.FAILED
    assert result.error == "input text is empty"
    assert result.logs[0]["level"] == "error"
    assert result.logs[0]["action"] == "input.rejected"
