#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent.multi_agent import MultiAgentLoop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Anubis planner/executor/critic loop.")
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("task", nargs="+")
    args = parser.parse_args()
    task = " ".join(args.task)
    print(json.dumps(MultiAgentLoop(max_rounds=args.max_rounds).run(task), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
