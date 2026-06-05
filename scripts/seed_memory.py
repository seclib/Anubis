from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from anubis.core_life.memory_life.semantic_memory import SemanticMemory


def main() -> None:
    memory = SemanticMemory()
    record = memory.remember("Seeded ANUBIS semantic memory for local development.")
    print(record.id)


if __name__ == "__main__":
    main()
