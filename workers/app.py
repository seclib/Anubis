"""Local worker process for Anubis maintenance tasks."""

from __future__ import annotations

import argparse
import json

from workers.jobs import background_once, crawl_once, maintain_vault, reindex_vault


def main() -> None:
    parser = argparse.ArgumentParser(description="Anubis worker")
    parser.add_argument("job", choices=["maintain-vault", "reindex-vault", "crawl-once", "background-once"])
    parser.add_argument("--query", default="cybersecurity osint research")
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()

    if args.job == "maintain-vault":
        result = maintain_vault()
    elif args.job == "reindex-vault":
        result = reindex_vault()
    elif args.job == "crawl-once":
        result = crawl_once(args.query, max_pages=args.max_pages)
    else:
        result = background_once()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
