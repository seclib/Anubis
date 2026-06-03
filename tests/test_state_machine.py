import json
import unittest

from anubis.distributed import (
    DistributedStateMachine,
    DistributedTaskState,
    EventBus,
    EventType,
    InMemoryStatePersistence,
    InvalidStateTransitionError,
    RedisStatePersistence,
    TaskStateNotFoundError,
    TransitionValidator,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def scan_iter(self, match: str):
        prefix = match.removesuffix("*")
        for key in sorted(self.values):
            if key.startswith(prefix):
                yield key


class DistributedStateMachineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        if hasattr(self, "event_bus"):
            await self.event_bus.drain()
            self.event_bus.close()

    async def test_state_machine_enforces_valid_transitions(self) -> None:
        state_machine = DistributedStateMachine()
        created = state_machine.create_task("task-1", metadata={"owner": "orchestrator"})

        self.assertEqual(created.state, DistributedTaskState.PENDING)
        planned = state_machine.transition("task-1", DistributedTaskState.PLANNED, reason="plan ready")
        executing = state_machine.transition("task-1", DistributedTaskState.EXECUTING)
        verifying = state_machine.transition("task-1", DistributedTaskState.VERIFYING)
        completed = state_machine.transition("task-1", DistributedTaskState.COMPLETED)

        self.assertEqual(planned.version, 1)
        self.assertEqual(executing.state, DistributedTaskState.EXECUTING)
        self.assertEqual(verifying.state, DistributedTaskState.VERIFYING)
        self.assertEqual(completed.state, DistributedTaskState.COMPLETED)

    async def test_state_machine_rejects_invalid_jumps_and_terminal_changes(self) -> None:
        state_machine = DistributedStateMachine()
        state_machine.create_task("task-2")

        with self.assertRaises(InvalidStateTransitionError):
            state_machine.transition("task-2", DistributedTaskState.COMPLETED)

        state_machine.transition("task-2", DistributedTaskState.FAILED)
        with self.assertRaises(InvalidStateTransitionError):
            state_machine.transition("task-2", DistributedTaskState.RETRYING)

    async def test_state_machine_persists_and_recovers_after_crash(self) -> None:
        persistence = InMemoryStatePersistence()
        first = DistributedStateMachine(persistence=persistence)
        first.create_task("task-3", metadata={"phase": "graph"})
        first.transition("task-3", DistributedTaskState.PLANNED, metadata={"plan_id": "plan-1"})

        recovered = DistributedStateMachine(persistence=persistence)
        record = recovered.get("task-3")

        self.assertEqual(record.state, DistributedTaskState.PLANNED)
        self.assertEqual(record.metadata["phase"], "graph")
        self.assertEqual(record.metadata["plan_id"], "plan-1")
        self.assertEqual(record.version, 1)

    async def test_state_change_triggers_event_bus(self) -> None:
        self.event_bus = EventBus()
        events = []
        self.event_bus.subscribe(EventType.TASK_STATE_CHANGED, events.append)
        state_machine = DistributedStateMachine(event_bus=self.event_bus)

        state_machine.create_task("task-4")
        state_machine.transition("task-4", DistributedTaskState.PLANNED, reason="planner finished")
        await self.event_bus.drain()

        self.assertEqual([event.event_type for event in events], [EventType.TASK_STATE_CHANGED, EventType.TASK_STATE_CHANGED])
        self.assertEqual(events[-1].payload["from"], "pending")
        self.assertEqual(events[-1].payload["to"], "planned")
        self.assertEqual(events[-1].payload["reason"], "planner finished")

    async def test_missing_task_cannot_be_bypassed(self) -> None:
        state_machine = DistributedStateMachine()

        with self.assertRaises(TaskStateNotFoundError):
            state_machine.transition("missing", DistributedTaskState.PLANNED)

    async def test_redis_persistence_adapter_round_trips_records(self) -> None:
        client = FakeRedis()
        persistence = RedisStatePersistence(client=client, key_prefix="test:state:")
        payload = {
            "task_id": "task-redis",
            "state": "executing",
            "version": 3,
            "metadata": {"worker": "executor-001"},
            "history": [],
            "updated_at": "now",
        }

        persistence.save("task-redis", payload)

        self.assertEqual(persistence.load("task-redis"), payload)
        self.assertEqual(persistence.load_all(), (payload,))
        raw = client.get("test:state:task-redis")
        self.assertEqual(json.loads(raw)["state"], "executing")

    async def test_transition_validator_exposes_allowed_targets(self) -> None:
        targets = TransitionValidator().allowed_targets(DistributedTaskState.VERIFYING)

        self.assertEqual(
            targets,
            (
                DistributedTaskState.BLOCKED,
                DistributedTaskState.COMPLETED,
                DistributedTaskState.FAILED,
                DistributedTaskState.RETRYING,
            ),
        )


if __name__ == "__main__":
    unittest.main()
