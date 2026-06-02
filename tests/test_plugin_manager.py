import json
import tempfile
from pathlib import Path
import unittest

from backend.skills.plugin_manager import (
    PLUGIN_MANIFEST_SCHEMA,
    PluginError,
    PluginLoader,
    PluginManager,
)


class PluginManagerTest(unittest.TestCase):
    def test_discovers_root_and_nested_plugin_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_plugin(root, "cybersec", ["security", "/\\bids\\b/"], ["cybersec"])
            (root / "cybersec" / "hardening.md").write_text(
                "# System Hardening\n\n## trigger\nUse for security hardening.",
                encoding="utf-8",
            )
            nested = root / "writer"
            nested.mkdir()
            (nested / "plugin.json").write_text(
                json.dumps({"name": "writer", "triggers": ["draft"], "skills": ["writer"]}),
                encoding="utf-8",
            )
            (nested / "style.md").write_text("# Style\n\nWrite clearly.", encoding="utf-8")

            manager = PluginManager(root=root)
            specs = manager.discover()

            self.assertEqual(set(specs), {"cybersec", "writer"})

    def test_routes_triggers_and_loads_skill_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_plugin(root, "cybersec", ["system hardening", "/\\bids\\b/"], ["cybersec"])
            (root / "cybersec" / "hardening.md").write_text(
                "# System Hardening\n\n## trigger\nUse when hardening Linux systems.",
                encoding="utf-8",
            )

            manager = PluginManager(root=root)
            resolved = manager.resolve("please do system hardening on this host")

            self.assertEqual(resolved["matches"], ("cybersec",))
            self.assertEqual(resolved["routes"][0]["trigger"], "system hardening")
            self.assertIn("System Hardening", resolved["active_context"][0]["skills"][0])

    def test_disable_and_enable_plugin_at_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_plugin(root, "cybersec", ["security"], ["cybersec"])
            (root / "cybersec" / "skill.md").write_text("# Security Skill\n", encoding="utf-8")
            manager = PluginManager(root=root)
            manager.discover()

            manager.disable("cybersec")
            disabled = manager.resolve("security review")

            self.assertEqual(disabled["matches"], ())
            self.assertFalse(manager.list_plugins()[0]["enabled"])

            manager.enable("cybersec")
            enabled = manager.resolve("security review")

            self.assertEqual(enabled["matches"], ("cybersec",))
            self.assertTrue(manager.list_plugins()[0]["enabled"])

    def test_manifest_validation_rejects_missing_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.plugin.json"
            path.write_text(json.dumps({"name": "bad", "skills": ["bad"]}), encoding="utf-8")

            with self.assertRaises(PluginError):
                PluginLoader(Path(tmp)).parse(path)

    def test_schema_exposes_required_contract(self) -> None:
        self.assertEqual(PLUGIN_MANIFEST_SCHEMA["required"], ["name", "triggers", "skills"])
        self.assertIn("permissions", PLUGIN_MANIFEST_SCHEMA["properties"])

    def test_plugin_skill_path_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_plugin(root, "escape", ["escape"], ["../outside.md"])
            manager = PluginManager(root=root)
            manager.discover()

            with self.assertRaises(ValueError):
                manager.load("escape")

    def _write_plugin(self, root: Path, name: str, triggers: list[str], skills: list[str]) -> None:
        manifest = {
            "name": name,
            "display_name": name.title(),
            "version": "1.0.0",
            "description": f"{name} plugin",
            "enabled": True,
            "triggers": triggers,
            "skills": skills,
            "memory": {"obsidian": [name], "qdrant": [name]},
            "permissions": {"tools": [], "network": False},
        }
        (root / f"{name}.plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        (root / name).mkdir(exist_ok=True)


if __name__ == "__main__":
    unittest.main()
