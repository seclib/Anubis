from __future__ import annotations

import atexit
import readline
from pathlib import Path

from router import ConsoleRouter


class AnubisConsole:
    def __init__(self, router: ConsoleRouter | None = None, history_file: Path | None = None) -> None:
        self.router = router or ConsoleRouter()
        self.history_file = history_file or Path("state/anubis_console_history")

    def run(self) -> int:
        self._setup_history()
        self._banner()
        while self.router.context.running:
            try:
                line = input(self.router.context.prompt).strip()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            result = self.router.route(line)
            if result.text:
                print(result.text)
            if not result.should_continue:
                break
        return 0

    def execute(self, commands: list[str]) -> int:
        for command in commands:
            result = self.router.route(command)
            if result.text:
                print(result.text)
            if not result.should_continue:
                return 130
        return 0

    def _setup_history(self) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(self.history_file)
        except FileNotFoundError:
            pass
        readline.set_history_length(2000)
        atexit.register(readline.write_history_file, self.history_file)

    def _banner(self) -> None:
        print("ANUBIS Console")
        print("Type help for commands, show modules to browse, exit to quit.")


def main() -> int:
    return AnubisConsole().run()
