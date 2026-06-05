from __future__ import annotations

from dataclasses import FrozenInstanceError

from core.graph import GraphRunStatus, GraphState, StateEngine


def test_state_engine_registers_global_state_versions_without_mutating_old_state() -> None:
    engine = StateEngine()
    initial_global = engine.current
    run_state = GraphState(run_id="run_state_001", stimulus="Investigate state drift")

    registered = engine.register_run(run_state, actor="test", reason="test registration")

    assert registered is not initial_global
    assert initial_global.version == 0
    assert registered.version == 1
    assert registered.get_run("run_state_001") == run_state
    assert registered.history[0].version == 1
    assert registered.transitions[0].changed_fields == ("run_states",)


def test_state_engine_transition_returns_new_global_state_and_tracks_changed_fields() -> None:
    engine = StateEngine()
    run_state = GraphState(run_id="run_state_002", stimulus="Investigate node transition")
    registered = engine.register_run(run_state)

    next_run_state = run_state.with_updates(status=GraphRunStatus.RUNNING)
    transitioned = engine.transition_run(
        next_run_state,
        actor="test",
        action="state.test.running",
        reason="test transition",
    )

    assert transitioned is not registered
    assert registered.version == 1
    assert transitioned.version == 2
    assert transitioned.get_run("run_state_002").status == GraphRunStatus.RUNNING
    assert "status" in transitioned.transitions[-1].changed_fields
    assert "updated_at" in transitioned.transitions[-1].changed_fields
    assert transitioned.transitions[-1].from_version == 1
    assert transitioned.transitions[-1].to_version == 2
    assert transitioned.transitions[-1].before_hash != transitioned.transitions[-1].after_hash


def test_state_engine_rejects_unregistered_transition_and_duplicate_run() -> None:
    engine = StateEngine()
    run_state = GraphState(run_id="run_state_003", stimulus="Investigate duplicate")
    engine.register_run(run_state)

    try:
        engine.register_run(run_state)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate run registration should fail")

    unknown = GraphState(run_id="run_state_unknown", stimulus="Investigate unknown")
    try:
        engine.transition_run(
            unknown,
            actor="test",
            action="state.test.unknown",
            reason="test missing registration",
        )
    except KeyError as exc:
        assert "must be registered" in str(exc)
    else:
        raise AssertionError("unregistered transition should fail")


def test_graph_state_is_frozen_and_transition_history_is_per_run() -> None:
    engine = StateEngine()
    first = GraphState(run_id="run_state_004", stimulus="First")
    second = GraphState(run_id="run_state_005", stimulus="Second")
    engine.register_run(first)
    engine.register_run(second)
    engine.transition_run(
        first.with_updates(status=GraphRunStatus.RUNNING),
        actor="test",
        action="state.test.first",
        reason="first transition",
    )

    try:
        first.status = GraphRunStatus.FAILED
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("GraphState should reject hidden mutation")

    assert len(engine.history_for_run("run_state_004")) == 2
    assert len(engine.history_for_run("run_state_005")) == 1
    assert len(engine.transitions_for_run("run_state_004")) == 2
