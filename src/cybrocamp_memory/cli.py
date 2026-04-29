from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .chunks import chunk_records_from_obsidian, load_chunk_manifest_jsonl, write_chunk_manifest_jsonl
from .eval_suite import run_eval_suite
from .graph_index import (
    load_term_graph_jsonl,
    recall_from_term_graph,
    term_graph_from_obsidian,
    write_term_graph_jsonl,
)
from .hermes_adapter import build_hermes_tool_response
from .hippo_core import hybrid_recall
from .manifest import manifest_records_from_obsidian, write_manifest_jsonl
from .rebuild import rebuild_all
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

    graph_index_parser = subparsers.add_parser("graph-index")
    graph_index_subparsers = graph_index_parser.add_subparsers(dest="source", required=True)
    graph_index_obsidian_parser = graph_index_subparsers.add_parser("obsidian")
    graph_index_obsidian_parser.add_argument("--vault", required=True)
    graph_index_obsidian_parser.add_argument("--output", required=True)
    graph_index_obsidian_parser.add_argument("--epoch", default="obsidian-scan-v1")
    graph_index_obsidian_parser.add_argument("--max-chars", type=int, default=1200)
    graph_index_obsidian_parser.add_argument("--max-terms-per-record", type=int, default=24)

    recall_graph_parser = subparsers.add_parser("recall-graph")
    recall_graph_parser.add_argument("--graph", required=True)
    recall_graph_parser.add_argument("--query", required=True)
    recall_graph_parser.add_argument("--output", required=True)
    recall_graph_parser.add_argument("--timestamp", default=None)
    recall_graph_parser.add_argument("--top-k", type=int, default=5)
    recall_graph_parser.add_argument("--max-depth", type=int, default=2)

    hippo_query_parser = subparsers.add_parser("hippo-query")
    hippo_query_parser.add_argument("--index", required=True)
    hippo_query_parser.add_argument("--graph", required=True)
    hippo_query_parser.add_argument("--query", required=True)
    hippo_query_parser.add_argument("--output", required=True)
    hippo_query_parser.add_argument("--timestamp", default=None)
    hippo_query_parser.add_argument("--top-k", type=int, default=8)
    hippo_query_parser.add_argument("--no-graph", action="store_true")

    rebuild_parser = subparsers.add_parser("rebuild-all")
    rebuild_parser.add_argument("--vault", required=True)
    rebuild_parser.add_argument("--output-dir", required=True)
    rebuild_parser.add_argument("--epoch", required=True)
    rebuild_parser.add_argument("--timestamp", required=True)
    rebuild_parser.add_argument("--max-chars", type=int, default=1200)
    rebuild_parser.add_argument("--max-terms-per-record", type=int, default=12)
    rebuild_parser.add_argument("--source-label", default=None)

    eval_suite_parser = subparsers.add_parser("eval-suite")
    eval_suite_parser.add_argument("--index", required=True)
    eval_suite_parser.add_argument("--graph", required=True)
    eval_suite_parser.add_argument("--cases", required=True)
    eval_suite_parser.add_argument("--output", required=True)
    eval_suite_parser.add_argument("--timestamp", required=True)
    eval_suite_parser.add_argument("--top-k", type=int, default=8)

    hermes_query_parser = subparsers.add_parser("hermes-query")
    hermes_query_parser.add_argument("--index", required=True)
    hermes_query_parser.add_argument("--graph", required=True)
    hermes_query_parser.add_argument("--query", required=True)
    hermes_query_parser.add_argument("--output", required=True)
    hermes_query_parser.add_argument("--timestamp", required=True)
    hermes_query_parser.add_argument("--top-k", type=int, default=8)
    hermes_query_parser.add_argument("--no-graph", action="store_true")

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
    if args.command == "graph-index" and args.source == "obsidian":
        created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        graph = term_graph_from_obsidian(
            Path(args.vault),
            max_chars=args.max_chars,
            max_terms_per_record=args.max_terms_per_record,
            epoch=args.epoch,
            created_at=created_at,
        )
        write_term_graph_jsonl(Path(args.output), graph.edges)
        print(f"wrote {len(graph.edges)} term graph edges to {args.output}")
        return 0
    if args.command == "recall-graph":
        timestamp = args.timestamp or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        graph = load_term_graph_jsonl(Path(args.graph))
        packet = recall_from_term_graph(
            graph,
            args.query,
            timestamp=timestamp,
            top_k=args.top_k,
            max_depth=args.max_depth,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(_packet_to_json_dict(packet), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(f"wrote graph recall packet with {len(packet.items)} items to {args.output}")
        return 0
    if args.command == "hippo-query":
        timestamp = args.timestamp or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        records = load_search_terms_jsonl(Path(args.index))
        graph = load_term_graph_jsonl(Path(args.graph))
        packet = hybrid_recall(
            records,
            graph,
            args.query,
            timestamp=timestamp,
            top_k=args.top_k,
            include_graph=not args.no_graph,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(_packet_to_json_dict(packet), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(f"wrote hippo recall packet with {len(packet.items)} items to {args.output}")
        return 0
    if args.command == "rebuild-all":
        result = rebuild_all(
            Path(args.vault),
            Path(args.output_dir),
            epoch=args.epoch,
            timestamp=args.timestamp,
            max_chars=args.max_chars,
            max_terms_per_record=args.max_terms_per_record,
            source_label=args.source_label,
        )
        print(
            "rebuilt "
            f"{result.record_counts['sources']} sources, "
            f"{result.record_counts['chunks']} chunks, "
            f"{result.record_counts['search_terms']} search records, "
            f"{result.record_counts['term_edges']} term edges into {args.output_dir}"
        )
        return 0
    if args.command == "eval-suite":
        result = run_eval_suite(
            index_path=Path(args.index),
            graph_path=Path(args.graph),
            cases_path=Path(args.cases),
            timestamp=args.timestamp,
            top_k=args.top_k,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result.to_json_dict(), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(f"wrote eval suite report with {result.case_count} cases to {args.output}")
        return 0 if result.passed else 1
    if args.command == "hermes-query":
        response = build_hermes_tool_response(
            index_path=Path(args.index),
            graph_path=Path(args.graph),
            query=args.query,
            timestamp=args.timestamp,
            top_k=args.top_k,
            include_graph=not args.no_graph,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(f"wrote Hermes tool response to {args.output}")
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
