import unittest

from cli.ux import render_block


class CliUxTest(unittest.TestCase):
    def test_render_block_enforces_sections(self) -> None:
        output = render_block("Status", {"builder": "idle", "orchestrator": "active"}, "runtime: ready")

        self.assertEqual(
            output,
            "TASK:\n"
            "Status\n"
            "\n"
            "STATUS:\n"
            "- builder: idle\n"
            "- orchestrator: active\n"
            "\n"
            "RESULT:\n"
            "runtime: ready\n"
            "\n",
        )


if __name__ == "__main__":
    unittest.main()
