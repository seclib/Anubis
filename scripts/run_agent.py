#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent.loop import AgentLoop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the minimal Anubis autonomous agent loop.")
    parser.add_argument("task", nargs="+")
    args = parser.parse_args()

    result = AgentLoop().chat(" ".join(args.task))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
