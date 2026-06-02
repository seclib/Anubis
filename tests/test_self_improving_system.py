import tempfile
from pathlib import Path
import unittest

from backend.skills.self_improving_pipeline import (
    FailureAnalyzer,
    PluginRegistrar,
    SelfImprovingSystem,
    SkillDeployer,
    SkillValidationSystem,
    ValidationResult,
)


class RejectingValidation(SkillValidationSystem):
    def validate(self, gap, generated, *, existing=()):
        result = ValidationResult(False, 0.2, ("critic rejected generated skill",))
        return result, result


class SelfImprovingSystemTest(unittest.TestCase):
    def test_analyzes_failures_detects_gap_generates_skill_and_registers_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            deployer = SkillDeployer(plugin_root=root, reindex=lambda: True, confirmed=True)
            system = SelfImprovingSystem(
                deployer=deployer,
                registrar=PluginRegistrar(deployer),
            )
            failures = [
                {
                    "ok": False,
                    "message": "missing firewall hardening workflow for SSH audit",
                    "confidence": 0.2,
                    "source": "run-1",
                },
                {
                    "ok": False,
                    "message": "missing firewall hardening workflow for inbound rules",
                    "confidence": 0.25,
                    "source": "run-2",
                },
            ]

            run = system.improve(failures, minimum_count=2)

            self.assertTrue(run.approved)
            self.assertEqual(len(run.gaps), 1)
            record = run.deployments[0]
            self.assertTrue(record.approved)
            self.assertTrue(Path(record.path).exists())
            self.assertTrue(Path(record.plugin_manifest).exists())
            markdown = Path(record.path).read_text(encoding="utf-8")
            self.assertIn("# skill:", markdown)
            self.assertIn("## dsl", markdown)

            resolved = system.registrar.manager.resolve("firewall hardening workflow")
            self.assertEqual(resolved["matches"], (record.name,))
            self.assertTrue(resolved["active_context"][0]["skills"])

    def test_critic_approval_is_required_before_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            deployer = SkillDeployer(plugin_root=root, reindex=lambda: True, confirmed=True)
            system = SelfImprovingSystem(
                validation=RejectingValidation(),
                deployer=deployer,
                registrar=PluginRegistrar(deployer),
            )
            failures = [
                {"ok": False, "message": "missing qdrant tuning workflow", "confidence": 0.1, "source": "a"},
                {"ok": False, "message": "missing qdrant tuning workflow", "confidence": 0.1, "source": "b"},
            ]

            run = system.improve(failures, minimum_count=2)

            self.assertFalse(run.approved)
            self.assertEqual(run.deployments[0].path, "")
            self.assertEqual(list(root.glob("*.plugin.json")), [])

    def test_failure_analyzer_extracts_repeated_missing_skill_signals(self) -> None:
        analyzer = FailureAnalyzer()

        analysis = analyzer.analyze(
            [
                {"ok": False, "error": "unknown playbook for log anomaly triage", "confidence": 0.3},
                {"ok": False, "error": "unknown playbook for log anomaly triage", "confidence": 0.3},
            ]
        )

        kinds = {signal.kind for signal in analysis.signals}
        self.assertIn("failed_task", kinds)
        self.assertIn("missing_knowledge", kinds)
        self.assertIn("repeated_error", kinds)


if __name__ == "__main__":
    unittest.main()
