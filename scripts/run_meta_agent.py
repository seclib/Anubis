#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent.meta_agent import MetaAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Anubis runs and propose validated improvements.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--auto-skill", action="store_true")
    args = parser.parse_args()
    print(json.dumps(MetaAgent().analyze(limit=args.limit, auto_skill=args.auto_skill), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
