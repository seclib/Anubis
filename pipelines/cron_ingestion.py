from __future__ import annotations

import argparse
import logging

from pipelines.update_pipeline import UpdatePipeline


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("anubis.pipelines.cron")


def main() -> None:
    parser = argparse.ArgumentParser(description="ANUBIS scheduled ingestion runner")
    parser.add_argument("--osint-jsonl")
    parser.add_argument("--nvd-json")
    parser.add_argument("--kev-json")
    parser.add_argument("--bugbounty-jsonl")
    parser.add_argument("--code-path")
    parser.add_argument("--stackoverflow-jsonl")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    pipeline = UpdatePipeline()
    total = 0
    if args.demo:
        total += pipeline.ingest_demo()
    if args.osint_jsonl:
        total += pipeline.ingest_osint_jsonl(args.osint_jsonl)
    if args.nvd_json:
        total += pipeline.ingest_nvd_json(args.nvd_json)
    if args.kev_json:
        total += pipeline.ingest_kev_json(args.kev_json)
    if args.bugbounty_jsonl:
        total += pipeline.ingest_bugbounty_jsonl(args.bugbounty_jsonl)
    if args.code_path:
        total += pipeline.ingest_code_path(args.code_path)
    if args.stackoverflow_jsonl:
        total += pipeline.ingest_stackoverflow_jsonl(args.stackoverflow_jsonl)
    logger.info("ingestion complete chunks=%s", total)


if __name__ == "__main__":
    main()
