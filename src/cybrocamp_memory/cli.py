from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .chunks import chunk_records_from_obsidian, load_chunk_manifest_jsonl, write_chunk_manifest_jsonl
from .manifest import manifest_records_from_obsidian, write_manifest_jsonl
from .retrieval import recall_query
from .search_index import (
    load_search_terms_jsonl,
    recall_from_search_terms,
    search_terms_from_obsidian,
    write_search_terms_jsonl,
)
from .schema import AuthorityClass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cybrocamp-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest")
    manifest_subparsers = manifest_parser.add_subparsers(dest="source", required=True)
    obsidian_parser = manifest_subparsers.add_parser("obsidian")
    obsidian_parser.add_argument("--vault", required=True)
    obsidian_parser.add_argument("--output", required=True)
    obsidian_parser.add_argument("--epoch", default="obsidian-scan-v1")

    chunks_parser = subparsers.add_parser("chunks")
    chunks_subparsers = chunks_parser.add_subparsers(dest="source", required=True)
    chunks_obsidian_parser = chunks_subparsers.add_parser("obsidian")
    chunks_obsidian_parser.add_argument("--vault", required=True)
    chunks_obsidian_parser.add_argument("--output", required=True)
    chunks_obsidian_parser.add_argument("--epoch", default="obsidian-scan-v1")
    chunks_obsidian_parser.add_argument("--max-chars", type=int, default=1200)

    recall_parser = subparsers.add_parser("recall")
    recall_parser.add_argument("--chunks", required=True)
    recall_parser.add_argument("--query", required=True)
    recall_parser.add_argument("--output", required=True)
    recall_parser.add_argument("--timestamp", default=None)
    recall_parser.add_argument("--top-k", type=int, default=5)

    search_index_parser = subparsers.add_parser("search-index")
    search_index_subparsers = search_index_parser.add_subparsers(dest="source", required=True)
    search_index_obsidian_parser = search_index_subparsers.add_parser("obsidian")
    search_index_obsidian_parser.add_argument("--vault", required=True)
    search_index_obsidian_parser.add_argument("--output", required=True)
    search_index_obsidian_parser.add_argument("--epoch", default="obsidian-scan-v1")
    search_index_obsidian_parser.add_argument("--max-chars", type=int, default=1200)

    recall_index_parser = subparsers.add_parser("recall-index")
    recall_index_parser.add_argument("--index", required=True)
    recall_index_parser.add_argument("--query", required=True)
    recall_index_parser.add_argument("--output", required=True)
    recall_index_parser.add_argument("--timestamp", default=None)
    recall_index_parser.add_argument("--top-k", type=int, default=5)

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
    if args.command == "chunks" and args.source == "obsidian":
        created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        records = list(
            chunk_records_from_obsidian(
                Path(args.vault),
                max_chars=args.max_chars,
                epoch=args.epoch,
                created_at=created_at,
            )
        )
        write_chunk_manifest_jsonl(Path(args.output), records)
        print(f"wrote {len(records)} chunk records to {args.output}")
        return 0
    if args.command == "recall":
        timestamp = args.timestamp or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        chunks = load_chunk_manifest_jsonl(Path(args.chunks))
        packet = recall_query(chunks, args.query, timestamp=timestamp, top_k=args.top_k)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(_packet_to_json_dict(packet), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(f"wrote recall packet with {len(packet.items)} items to {args.output}")
        return 0
    if args.command == "search-index" and args.source == "obsidian":
        created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        records = search_terms_from_obsidian(
            Path(args.vault),
            max_chars=args.max_chars,
            epoch=args.epoch,
            created_at=created_at,
        )
        write_search_terms_jsonl(Path(args.output), records)
        print(f"wrote {len(records)} search term records to {args.output}")
        return 0
    if args.command == "recall-index":
        timestamp = args.timestamp or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        records = load_search_terms_jsonl(Path(args.index))
        packet = recall_from_search_terms(records, args.query, timestamp=timestamp, top_k=args.top_k)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(_packet_to_json_dict(packet), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(f"wrote indexed recall packet with {len(packet.items)} items to {args.output}")
        return 0
    parser.error("unsupported command")
    return 2


def _packet_to_json_dict(packet) -> dict[str, object]:
    data = asdict(packet)
    for item in data["items"]:
        if isinstance(item["authority"], AuthorityClass):
            item["authority"] = item["authority"].value
        evidence = item["evidence"]
        if isinstance(evidence.get("authority"), AuthorityClass):
            evidence["authority"] = evidence["authority"].value
    return data


if __name__ == "__main__":
    raise SystemExit(main())
