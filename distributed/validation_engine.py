"""Validation engine for distributed Reviewer Agent."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from anubis.distributed.rollback import ReviewRecommendation


@dataclass(frozen=True)
class ReviewInput:
    step_id: str
    execution_success: bool
    output: str
    logs: tuple[str, ...] = ()
    expected: dict[str, Any] = field(default_factory=dict)
    file_checks: tuple[dict[str, Any], ...] = ()
    command_checks: tuple[dict[str, Any], ...] = ()
    state_checks: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ReviewInput":
        step_id = payload.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError("review input requires a non-empty step_id")

        return cls(
            step_id=step_id.strip(),
            execution_success=bool(payload.get("success", payload.get("execution_success", False))),
            output=_stringify(payload.get("output", "")),
            logs=tuple(str(log) for log in payload.get("logs", []) if log is not None),
            expected=dict(payload.get("expected", {}) or {}),
            file_checks=_tuple_of_dicts(payload.get("file_checks", ())),
            command_checks=_tuple_of_dicts(payload.get("command_checks", ())),
            state_checks=_tuple_of_dicts(payload.get("state_checks", ())),
        )


@dataclass(frozen=True)
class ReviewResult:
    step_id: str
    valid: bool
    issues: tuple[str, ...]
    recommendation: ReviewRecommendation

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "valid": self.valid,
            "issues": list(self.issues),
            "recommendation": self.recommendation.value,
        }


class ValidationEngine:
    """Pure validation logic for execution outputs and supplied evidence."""

    def validate(self, review_input: ReviewInput) -> ReviewResult:
        issues: list[str] = []

        if not review_input.execution_success:
            issues.append("execution result reports failure")

        issues.extend(self._validate_expected_output(review_input))
        issues.extend(self._validate_file_integrity(review_input.file_checks))
        issues.extend(self._validate_command_success(review_input.command_checks))
        issues.extend(self._validate_state(review_input.state_checks))

        recommendation = self._recommendation(issues)
        return ReviewResult(
            step_id=review_input.step_id,
            valid=not issues,
            issues=tuple(issues),
            recommendation=recommendation,
        )

    def _validate_expected_output(self, review_input: ReviewInput) -> list[str]:
        issues: list[str] = []
        expected = review_input.expected
        contains = expected.get("contains", ())
        if isinstance(contains, str):
            contains = (contains,)
        for token in contains:
            if isinstance(token, str) and token not in review_input.output:
                issues.append(f"expected output missing: {token}")

        equals = expected.get("equals")
        if isinstance(equals, str) and review_input.output != equals:
            issues.append("actual output does not match expected output")
        return issues

    def _validate_file_integrity(self, file_checks: tuple[dict[str, Any], ...]) -> list[str]:
        issues: list[str] = []
        for check in file_checks:
            path = str(check.get("path", "unknown"))
            if check.get("exists") is False:
                issues.append(f"file integrity failed: {path} missing")
            if check.get("valid") is False:
                issues.append(f"file integrity failed: {path} invalid")
            if check.get("checksum_match") is False:
                issues.append(f"file integrity failed: {path} checksum mismatch")
        return issues

    def _validate_command_success(self, command_checks: tuple[dict[str, Any], ...]) -> list[str]:
        issues: list[str] = []
        for check in command_checks:
            command = str(check.get("cmd", check.get("command", "command")))
            if check.get("success") is False:
                issues.append(f"command failed: {command}")
            code = check.get("code")
            if isinstance(code, int) and code != 0:
                issues.append(f"command exited non-zero: {command} ({code})")
            if check.get("timed_out") is True:
                issues.append(f"command timed out: {command}")
        return issues

    def _validate_state(self, state_checks: tuple[dict[str, Any], ...]) -> list[str]:
        issues: list[str] = []
        for check in state_checks:
            name = str(check.get("name", "state"))
            if check.get("broken") is True:
                issues.append(f"broken state detected: {name}")
            if check.get("actual") != check.get("expected") and "expected" in check:
                issues.append(f"state mismatch: {name}")
        return issues

    def _recommendation(self, issues: list[str]) -> ReviewRecommendation:
        if not issues:
            return ReviewRecommendation.APPROVE
        rollback_markers = (
            "broken state",
            "file integrity failed",
        )
        if any(any(marker in issue for marker in rollback_markers) for issue in issues):
            return ReviewRecommendation.ROLLBACK
        return ReviewRecommendation.RETRY


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _tuple_of_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


__all__ = ["ReviewInput", "ReviewResult", "ValidationEngine"]
