import os
import unittest
from unittest.mock import patch

from anubis.cli.formatter import format_error, format_output
from anubis.cli.prompt import render_prompt


class AnubisCliTerminalTest(unittest.TestCase):
    def test_prompt_is_plain_by_default(self) -> None:
        self.assertEqual(render_prompt(), "anubis >")

    def test_prompt_can_be_compact(self) -> None:
        with patch.dict(os.environ, {"ANUBIS_CLI_PROMPT": ">"}, clear=False):
            self.assertEqual(render_prompt(), ">")

    def test_prompt_rejects_decorative_values(self) -> None:
        with patch.dict(os.environ, {"ANUBIS_CLI_PROMPT": "anubis ~/repo model >"}, clear=False):
            self.assertEqual(render_prompt(), "anubis >")

    def test_prompt_never_emits_ansi(self) -> None:
        with patch.dict(os.environ, {"ANUBIS_CLI_COLOR": "always"}, clear=False):
            self.assertNotIn("\033", render_prompt())

    def test_output_uses_required_sections(self) -> None:
        output = format_output("Status", {"builder": "idle"}, "runtime: ready")

        self.assertEqual(
            output,
            "TASK:\n"
            "Status\n"
            "\n"
            "STATUS:\n"
            "builder: idle\n"
            "\n"
            "RESULT:\n"
            "runtime: ready\n",
        )

    def test_error_uses_required_sections(self) -> None:
        output = format_error("Command execution", "failed")

        self.assertEqual(
            output,
            "TASK:\n"
            "Command execution\n"
            "\n"
            "STATUS:\n"
            "error\n"
            "\n"
            "RESULT:\n"
            "failed\n",
        )


if __name__ == "__main__":
    unittest.main()
