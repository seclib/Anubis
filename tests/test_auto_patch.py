from datetime import datetime, timezone
import unittest

from anubis.distributed import (
    AttackExecutionResult,
    AttackExecutionStatus,
    AutoPatchGenerator,
    AutoPatchRequest,
    AutoPatchStage,
    DefenseAnalysisReport,
    DefenseFinding,
    DefenseGrade,
    DefenseMetrics,
    ExploitPathFinder,
    ExploitPathKind,
    FixProposalEngine,
    PatchProposalStatus,
    SOCEvent,
    TaskGraph,
    TaskGraphNode,
    TaskGraphNodeType,
)


class RecordingPatchPipeline:
    def __init__(self, *, fail_ci: bool = False, fail_red_team: bool = False) -> None:
        self.fail_ci = fail_ci
        self.fail_red_team = fail_red_team
        self.calls: list[tuple[str, str, object]] = []

    def submit_pr(self, proposal, request):
        self.calls.append(("pr", proposal.proposal_id, request))
        return {"success": True, "request": request.to_dict()}

    def run_ci(self, proposal, pr_result):
        self.calls.append(("ci", proposal.proposal_id, pr_result))
        return {"success": not self.fail_ci, "checks": [{"name": "tests", "success": not self.fail_ci}]}

    def rerun_red_team(self, proposal, ci_result):
        self.calls.append(("red_team", proposal.proposal_id, ci_result))
        return {"success": not self.fail_red_team, "validated": not self.fail_red_team}


def exploit_report():
    graph = TaskGraph(
        task_id="feature-001",
        nodes=(
            TaskGraphNode("plan", TaskGraphNodeType.PLAN),
            TaskGraphNode("deploy", TaskGraphNodeType.EXECUTE, depends_on=("plan",), payload={"step_type": "shell", "action": "deploy command"}),
        ),
    )
    result = AttackExecutionResult(
        attack_id="attack-tool",
        attack_type="tool_abuse",
        target="executor",
        status=AttackExecutionStatus.CONTAINED,
        success=True,
        sandbox_id="sandbox-1",
        system_response={
            "contained": True,
            "execution_type": "permission_bypass_attempt",
            "denied_permissions": [{"tool": "admin_shell", "approved": False}],
        },
    )
    return ExploitPathFinder().analyze(task_graph=graph, attack_results=[result])


def defense_report():
    metrics = DefenseMetrics(
        attacks_total=1,
        attacks_contained=0,
        detections_total=0,
        blocked_actions=0,
        kill_switch_triggers=0,
        false_negatives=1,
        detection_speed_ms=None,
        containment_success_rate=0,
        detection_rate=0,
        resilience_score=10,
    )
    return DefenseAnalysisReport(
        grade=DefenseGrade.FAIL,
        metrics=metrics,
        findings=(
            DefenseFinding(
                code="containment_gap",
                severity="critical",
                message="one or more simulated attacks were not contained",
                evidence={"contained": 0, "total": 1},
            ),
        ),
    )


class AutoPatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_fix_proposal_engine_generates_patches_from_exploit_paths(self) -> None:
        proposals = FixProposalEngine().propose(exploit_report(), validation_commands=("pytest tests/security",))

        titles = {proposal.title for proposal in proposals}

        self.assertIn("Harden tool permission boundary", titles)
        self.assertTrue(any("weak_link" in proposal.metadata for proposal in proposals))
        self.assertTrue(all(proposal.status == PatchProposalStatus.PROPOSED for proposal in proposals))
        self.assertTrue(all(proposal.validation_commands == ("pytest tests/security",) for proposal in proposals))

    async def test_auto_patch_without_pipeline_returns_proposals_only(self) -> None:
        result = await AutoPatchGenerator().run(AutoPatchRequest(exploit_report()))

        self.assertTrue(result.success)
        self.assertEqual(result.stage, AutoPatchStage.PROPOSED)
        self.assertGreaterEqual(len(result.proposals), 1)
        self.assertEqual(result.pr_results, ())
        self.assertEqual(result.ci_results, ())
        self.assertEqual(result.red_team_results, ())

    async def test_auto_patch_sends_proposals_through_pr_ci_and_red_team_validation(self) -> None:
        pipeline = RecordingPatchPipeline()
        result = await AutoPatchGenerator(pipeline=pipeline).run(
            AutoPatchRequest(
                exploit_report(),
                repo_path="/repos/anubis",
                base_branch="main",
                create_remote_pr=False,
                validation_commands=("pytest tests/security",),
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.stage, AutoPatchStage.RED_TEAM_VALIDATED)
        self.assertTrue(all(proposal.status == PatchProposalStatus.SUBMITTED for proposal in result.proposals))
        self.assertEqual([call[0] for call in pipeline.calls], ["pr", "ci", "red_team", "pr", "ci", "red_team"])
        pr_request = pipeline.calls[0][2]
        self.assertEqual(pr_request.repo_path, "/repos/anubis")
        self.assertEqual(pr_request.validation_commands, ("pytest tests/security",))
        self.assertFalse(pr_request.create_remote)
        self.assertIn("auto-patch", pr_request.labels)

    async def test_auto_patch_fails_closed_when_ci_rejects_patch(self) -> None:
        pipeline = RecordingPatchPipeline(fail_ci=True)
        result = await AutoPatchGenerator(pipeline=pipeline).run(AutoPatchRequest(exploit_report()))

        self.assertFalse(result.success)
        self.assertEqual(result.stage, AutoPatchStage.FAILED)
        self.assertEqual(result.error, "CI/CD validation failed")
        self.assertEqual([call[0] for call in pipeline.calls], ["pr", "ci"])

    async def test_defense_report_generates_containment_fix_proposal(self) -> None:
        proposals = FixProposalEngine().propose(defense_report())

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].title, "Strengthen containment enforcement")
        self.assertEqual(proposals[0].changes[0].target, "sandbox_runtime")
        self.assertGreaterEqual(proposals[0].probability, 1)

    async def test_result_serializes_pipeline_outputs(self) -> None:
        result = await AutoPatchGenerator(pipeline=RecordingPatchPipeline()).run(AutoPatchRequest(defense_report()))
        payload = result.to_dict()

        self.assertTrue(payload["success"])
        self.assertEqual(payload["stage"], "red_team_validated")
        self.assertEqual(payload["pr_results"][0]["success"], True)
        self.assertIn("fix_proposal", payload["pr_results"][0]["request"]["metadata"])


if __name__ == "__main__":
    unittest.main()
