import unittest

from anubis.distributed import (
    EventBus,
    EventType,
    FailureMonitor,
    KillSwitchActiveError,
    KillSwitchController,
    KillSwitchGuardedExecutor,
    KillSwitchState,
    KillTrigger,
    ProcessRegistry,
    RecoveryMode,
    RecoveryStateManager,
)


class FakeProcess:
    def __init__(self, *, exits_on_terminate=True) -> None:
        self.running = True
        self.exits_on_terminate = exits_on_terminate
        self.terminated = False
        self.killed = False
        self.joins = 0

    def is_alive(self):
        return self.running

    def terminate(self):
        self.terminated = True
        if self.exits_on_terminate:
            self.running = False

    def kill(self):
        self.killed = True
        self.running = False

    def join(self, timeout=None):
        self.joins += 1


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "output": "executed", "logs": []}


class KillSwitchTest(unittest.TestCase):
    def test_manual_trigger_enters_recovery_and_blocks_execution(self) -> None:
        controller = KillSwitchController()

        status = controller.manual_trigger("operator requested stop")

        self.assertEqual(status.state, KillSwitchState.RECOVERY)
        self.assertEqual(status.recovery_mode, RecoveryMode.INSPECTION_ONLY)
        self.assertEqual(status.triggered_by, KillTrigger.MANUAL)
        self.assertFalse(status.execution_allowed)
        self.assertFalse(status.queue_processing_allowed)
        with self.assertRaises(KillSwitchActiveError):
            controller.assert_execution_allowed()
        with self.assertRaises(KillSwitchActiveError):
            controller.assert_queue_processing_allowed()

    def test_repeated_failures_trigger_kill_switch_at_threshold(self) -> None:
        controller = KillSwitchController(failure_monitor=FailureMonitor(threshold=3))

        self.assertIsNone(controller.record_failure(source="executor-1", reason="test failed"))
        self.assertIsNone(controller.record_failure(source="executor-2", reason="lint failed"))
        status = controller.record_failure(source="executor-3", reason="sandbox crashed")

        self.assertIsNotNone(status)
        self.assertEqual(status.triggered_by, KillTrigger.REPEATED_FAILURES)
        self.assertIn("failure threshold reached", status.reason)
        self.assertEqual(controller.state, KillSwitchState.RECOVERY)

    def test_unsafe_file_access_triggers_immediately(self) -> None:
        controller = KillSwitchController()

        status = controller.record_unsafe_file_access(
            path="/etc/passwd",
            source="filesystem-jail",
            reason="absolute path escape",
        )

        self.assertEqual(status.triggered_by, KillTrigger.UNSAFE_FILE_ACCESS)
        self.assertEqual(status.source, "filesystem-jail")
        snapshot = controller.recovery_manager.snapshot()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.record.metadata["path"], "/etc/passwd")

    def test_system_instability_triggers_immediately(self) -> None:
        controller = KillSwitchController()

        status = controller.record_instability(source="health-monitor", reason="queue corruption detected")

        self.assertEqual(status.triggered_by, KillTrigger.SYSTEM_INSTABILITY)
        self.assertFalse(status.execution_allowed)

    def test_trigger_cancels_registered_sandbox_processes(self) -> None:
        registry = ProcessRegistry()
        graceful = FakeProcess(exits_on_terminate=True)
        stubborn = FakeProcess(exits_on_terminate=False)
        registry.register("sandbox-1", graceful)
        registry.register("sandbox-2", stubborn)
        controller = KillSwitchController(process_registry=registry)

        status = controller.manual_trigger("unsafe behavior")

        self.assertEqual(status.cancelled_processes, ("sandbox-1", "sandbox-2"))
        self.assertTrue(graceful.terminated)
        self.assertFalse(graceful.killed)
        self.assertTrue(stubborn.terminated)
        self.assertTrue(stubborn.killed)
        self.assertEqual(registry.active_ids(), ())

    def test_guarded_executor_denies_delegate_after_kill_switch(self) -> None:
        controller = KillSwitchController()
        delegate = RecordingExecutor()
        guarded = KillSwitchGuardedExecutor(controller, delegate)

        allowed = guarded.execute(task_id="task-1", tool="run_command")
        controller.manual_trigger("stop execution")
        denied = guarded.execute(task_id="task-2", tool="run_command")

        self.assertTrue(allowed["success"])
        self.assertFalse(denied["success"])
        self.assertIn("kill switch active", denied["logs"])
        self.assertEqual(len(delegate.calls), 1)

    def test_recovery_state_freezes_snapshot_for_inspection_only(self) -> None:
        recovery = RecoveryStateManager()
        controller = KillSwitchController(recovery_manager=recovery)

        controller.trigger(
            KillTrigger.MANUAL,
            "freeze for inspection",
            source="operator",
            frozen_state={"queue_depth": 7, "running_tasks": ["task-1"]},
        )

        snapshot = recovery.snapshot()
        self.assertIsNotNone(snapshot)
        self.assertEqual(recovery.mode, RecoveryMode.INSPECTION_ONLY)
        self.assertEqual(snapshot.frozen_state["queue_depth"], 7)
        self.assertEqual(snapshot.frozen_state["running_tasks"], ["task-1"])
        with self.assertRaises(KillSwitchActiveError):
            recovery.assert_execution_allowed()

    def test_kill_switch_publishes_shutdown_event(self) -> None:
        bus = EventBus()
        controller = KillSwitchController(event_bus=bus)

        controller.manual_trigger("operator stop")

        events = bus.events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, EventType.TASK_FAILED)
        self.assertEqual(events[0].task_id, "global-kill-switch")
        self.assertEqual(events[0].payload["state"], "recovery")


if __name__ == "__main__":
    unittest.main()
