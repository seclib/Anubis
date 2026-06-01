#!/usr/bin/env python3
import sys
from pathlib import Path
import argparse


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.watcher.markdown_watcher import run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch Obsidian Markdown files and sync them into vector memory.")
    parser.add_argument("--debounce", type=float, default=0.5)
    args = parser.parse_args()
    run(debounce_seconds=args.debounce)
