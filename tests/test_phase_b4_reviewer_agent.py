import unittest

from anubis.distributed import (
    ReviewerAgent,
    ReviewRecommendation,
    RollbackSignalCollector,
    ValidationEngine,
)


class PhaseB4ReviewerAgentTest(unittest.TestCase):
    def test_reviewer_approves_valid_execution_result(self) -> None:
        result = ReviewerAgent().review_dict(
            {
                "step_id": "step_001",
                "success": True,
                "output": "tests passed and file updated",
                "logs": ["executor completed"],
                "expected": {"contains": ["tests passed"]},
                "file_checks": [{"path": "module.py", "exists": True, "valid": True}],
                "command_checks": [{"cmd": "python -m unittest", "code": 0, "timed_out": False}],
                "state_checks": [{"name": "workspace", "expected": "clean", "actual": "clean"}],
            }
        )

        self.assertEqual(
            result,
            {
                "step_id": "step_001",
                "valid": True,
                "issues": [],
                "recommendation": "approve",
            },
        )

    def test_reviewer_retries_failed_command_or_expected_output_mismatch(self) -> None:
        result = ReviewerAgent().review(
            {
                "step_id": "step_002",
                "success": True,
                "output": "partial result",
                "expected": {"contains": ["complete result"]},
                "command_checks": [{"cmd": "python -m unittest", "code": 1}],
            }
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.recommendation, ReviewRecommendation.RETRY)
        self.assertIn("expected output missing: complete result", result.issues)
        self.assertIn("command exited non-zero: python -m unittest (1)", result.issues)

    def test_reviewer_emits_rollback_signal_for_broken_state(self) -> None:
        signals = RollbackSignalCollector()
        reviewer = ReviewerAgent(rollback_signals=signals)

        result = reviewer.review(
            {
                "step_id": "step_003",
                "success": True,
                "output": "write completed",
                "file_checks": [{"path": "important.py", "checksum_match": False}],
                "state_checks": [{"name": "imports", "broken": True}],
            }
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.recommendation, ReviewRecommendation.ROLLBACK)
        self.assertEqual(len(signals.signals()), 1)
        self.assertEqual(signals.signals()[0].step_id, "step_003")
        self.assertIn("checksum mismatch", signals.signals()[0].reason)

    def test_reviewer_rejects_execution_failure_without_rollback_marker(self) -> None:
        result = ReviewerAgent().review_dict(
            {
                "step_id": "step_004",
                "success": False,
                "output": "tool failed",
                "logs": ["failure"],
            }
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["recommendation"], "retry")
        self.assertEqual(result["issues"], ["execution result reports failure"])

    def test_reviewer_handles_malformed_payload_as_retry(self) -> None:
        result = ReviewerAgent().review_dict({"success": True, "output": "missing step id"})

        self.assertEqual(result["step_id"], "")
        self.assertFalse(result["valid"])
        self.assertEqual(result["recommendation"], "retry")
        self.assertIn("non-empty step_id", result["issues"][0])

    def test_validation_engine_is_pure_and_deterministic(self) -> None:
        payload = {
            "step_id": "step_005",
            "success": True,
            "output": "same",
            "expected": {"equals": "same"},
        }
        first = ReviewerAgent(validation_engine=ValidationEngine()).review_dict(payload)
        second = ReviewerAgent(validation_engine=ValidationEngine()).review_dict(payload)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
