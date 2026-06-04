import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from modules.osint.adapter.osint_skill import OsintSkillAdapter, discover_skill_path, normalize_skill_output
from modules.osint.schemas import OsintInput


class OsintModuleTest(unittest.TestCase):
    def test_discovers_sibling_osint_skill_repository(self) -> None:
        ai_root = Path(__file__).resolve().parents[2]
        self.assertEqual(discover_skill_path(), ai_root / "osint-skill")

    def test_normalizes_handle_and_platform_mentions(self) -> None:
        report = normalize_skill_output(
            "@alice",
            "\n".join(
                [
                    "https://www.linkedin.com/in/alice",
                    "https://x.com/alice",
                    "https://www.linkedin.com/in/alice",
                ]
            ),
        ).to_dict()

        self.assertEqual(report["identity"]["usernames"], ["alice"])
        self.assertEqual(report["footprint"]["platforms"], ["linkedin", "twitter/x"])
        self.assertEqual(len(report["footprint"]["mentions"]), 2)
        self.assertGreater(report["analysis"]["confidence"], 0.0)

    def test_normalizes_profile_url_identity(self) -> None:
        report = normalize_skill_output("https://github.com/octocat", "").to_dict()

        self.assertEqual(report["identity"]["aliases"], ["github.com"])
        self.assertEqual(report["identity"]["usernames"], ["octocat"])
        self.assertEqual(report["analysis"]["confidence"], 0.0)

    def test_adapter_executes_external_skill_scripts(self) -> None:
        with TemporaryDirectory() as tmp:
            skill = Path(tmp)
            scripts = skill / "scripts"
            scripts.mkdir()
            (scripts / "diagnose.sh").write_text("#!/bin/bash\necho diagnostic-ok\n", encoding="utf-8")
            (scripts / "first-volley.sh").write_text(
                "#!/bin/bash\n"
                "mkdir -p /tmp/osint-test\n"
                "echo 'Output: /tmp/osint-test/'\n",
                encoding="utf-8",
            )
            (scripts / "merge-volley.sh").write_text(
                "#!/bin/bash\n"
                "echo 'https://www.linkedin.com/in/alice'\n"
                "echo 'https://github.com/alice'\n",
                encoding="utf-8",
            )

            execution = OsintSkillAdapter(skill_path=skill, timeout_seconds=5).execute(OsintInput(target="@alice"))

        report = execution.report.to_dict()
        self.assertEqual(report["identity"]["usernames"], ["alice"])
        self.assertEqual(report["footprint"]["platforms"], ["linkedin", "github"])
        self.assertEqual(len(report["footprint"]["mentions"]), 2)


if __name__ == "__main__":
    unittest.main()
