from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .manifest import manifest_records_from_obsidian, write_manifest_jsonl


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cybrocamp-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest")
    manifest_subparsers = manifest_parser.add_subparsers(dest="source", required=True)
    obsidian_parser = manifest_subparsers.add_parser("obsidian")
    obsidian_parser.add_argument("--vault", required=True)
    obsidian_parser.add_argument("--output", required=True)
    obsidian_parser.add_argument("--epoch", default="obsidian-scan-v1")

    args = parser.parse_args(argv)
    if args.command == "manifest" and args.source == "obsidian":
        created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        records = list(
            manifest_records_from_obsidian(
                Path(args.vault),
                epoch=args.epoch,
                created_at=created_at,
            )
        )
        write_manifest_jsonl(Path(args.output), records)
        print(f"wrote {len(records)} source records to {args.output}")
        return 0
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
