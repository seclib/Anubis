#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.skills.engine import SkillEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Observe repeated tasks and generate reusable Anubis skills.")
    parser.add_argument("task", nargs="*")
    parser.add_argument("--outcome", default="")
    parser.add_argument("--improve", action="store_true")
    args = parser.parse_args()

    engine = SkillEngine()
    if args.improve:
        result = engine.improve_from_memory()
    else:
        if not args.task:
            parser.error("task is required unless --improve is used")
        result = engine.observe(" ".join(args.task), outcome=args.outcome)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
