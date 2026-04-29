from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .chunks import chunk_records_from_obsidian, load_chunk_manifest_jsonl, write_chunk_manifest_jsonl
from .eval_suite import run_eval_suite
from .fact_cache import load_fact_cache_jsonl
from .graph_index import (
    load_term_graph_jsonl,
    recall_from_term_graph,
    term_graph_from_obsidian,
    write_term_graph_jsonl,
)
from .hermes_adapter import build_hermes_tool_response
from .hippo_core import hybrid_recall
from .local_api import (
    build_api_bundle,
    build_api_status,
    build_query_response,
    run_local_api,
    write_api_bundle,
    write_api_json_response,
)
from .manifest import manifest_records_from_obsidian, write_manifest_jsonl
from .operational_persistence import build_persistence_bundle, write_persistence_bundle
from .promotion_audit import audit_promotion_candidates, write_promotion_audit_json
from .promotion_execution import build_execution_receipt, write_execution_receipt_json
from .promotion_plan import build_promotion_plan, write_promotion_plan_json
from .promotion_preview import build_locked_preview, write_locked_preview_json
from .rebuild import rebuild_all
from .sister_rollout import build_cortex_rollout, write_cortex_rollout_json
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

    promotion_audit_parser = subparsers.add_parser("promotion-audit")
    promotion_audit_parser.add_argument("--facts", required=True)
    promotion_audit_parser.add_argument("--output", required=True)
    promotion_audit_parser.add_argument("--timestamp", required=True)
    promotion_audit_parser.add_argument("--current-source-hashes", default=None)
    promotion_audit_parser.add_argument("--current-chunk-hashes", default=None)
    promotion_audit_parser.add_argument("--mempalace-comparison", default=None)

    promotion_plan_parser = subparsers.add_parser("promotion-plan")
    promotion_plan_parser.add_argument("--audit", required=True)
    promotion_plan_parser.add_argument("--output", required=True)
    promotion_plan_parser.add_argument("--timestamp", required=True)
    promotion_plan_parser.add_argument("--approval-scope", default=None)

    promotion_preview_parser = subparsers.add_parser("promotion-preview")
    promotion_preview_parser.add_argument("--plan", required=True)
    promotion_preview_parser.add_argument("--output", required=True)
    promotion_preview_parser.add_argument("--timestamp", required=True)
    promotion_preview_parser.add_argument("--lock-scope", default=None)

    promotion_execute_parser = subparsers.add_parser("promotion-execute")
    promotion_execute_parser.add_argument("--preview", required=True)
    promotion_execute_parser.add_argument("--output", required=True)
    promotion_execute_parser.add_argument("--timestamp", required=True)
    promotion_execute_parser.add_argument("--execution-approval", default=None)

    cortex_rollout_parser = subparsers.add_parser("cortex-rollout")
    cortex_rollout_parser.add_argument("--output", required=True)
    cortex_rollout_parser.add_argument("--timestamp", required=True)

    persistence_parser = subparsers.add_parser("persistence-bundle")
    persistence_parser.add_argument("--repo-root", required=True)
    persistence_parser.add_argument("--vault", required=True)
    persistence_parser.add_argument("--artifact-root", required=True)
    persistence_parser.add_argument("--output-dir", required=True)
    persistence_parser.add_argument("--interval-minutes", type=int, default=30)

    api_status_parser = subparsers.add_parser("local-api-status")
    api_status_parser.add_argument("--artifact-dir", required=True)
    api_status_parser.add_argument("--output", default=None)
    api_status_parser.add_argument("--timestamp", required=True)

    api_query_parser = subparsers.add_parser("local-api-query")
    api_query_parser.add_argument("--artifact-dir", required=True)
    api_query_parser.add_argument("--query", required=True)
    api_query_parser.add_argument("--output", required=True)
    api_query_parser.add_argument("--timestamp", required=True)
    api_query_parser.add_argument("--top-k", type=int, default=8)
    api_query_parser.add_argument("--no-graph", action="store_true")

    api_bundle_parser = subparsers.add_parser("local-api-bundle")
    api_bundle_parser.add_argument("--repo-root", required=True)
    api_bundle_parser.add_argument("--artifact-dir", required=True)
    api_bundle_parser.add_argument("--output-dir", required=True)
    api_bundle_parser.add_argument("--host", default="127.0.0.1")
    api_bundle_parser.add_argument("--port", type=int, default=8765)
    api_bundle_parser.add_argument("--auth-token-file", default=None)

    api_server_parser = subparsers.add_parser("local-api")
    api_server_parser.add_argument("--artifact-dir", required=True)
    api_server_parser.add_argument("--host", default="127.0.0.1")
    api_server_parser.add_argument("--port", type=int, default=8765)
    api_server_parser.add_argument("--auth-token-file", default=None)

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
    if args.command == "promotion-audit":
        facts = load_fact_cache_jsonl(Path(args.facts))
        report = audit_promotion_candidates(
            facts,
            current_source_hashes=_load_json_object(args.current_source_hashes),
            current_chunk_hashes=_load_json_object(args.current_chunk_hashes),
            mempalace_comparisons=_load_json_list(args.mempalace_comparison),
            timestamp=args.timestamp,
        )
        write_promotion_audit_json(Path(args.output), report)
        print(f"wrote promotion audit report with {len(report.items)} items to {args.output}")
        return 0
    if args.command == "promotion-plan":
        audit_report = json.loads(Path(args.audit).read_text(encoding="utf-8"))
        if not isinstance(audit_report, dict):
            raise ValueError("expected promotion audit JSON object")
        plan = build_promotion_plan(
            audit_report,
            approval_scope=_load_json_mapping(args.approval_scope),
            timestamp=args.timestamp,
        )
        write_promotion_plan_json(Path(args.output), plan)
        print(f"wrote promotion plan with {len(plan.dry_run_ops)} dry-run ops to {args.output}")
        return 0
    if args.command == "promotion-preview":
        plan_data = _load_required_json_mapping(args.plan, "promotion plan")
        preview = build_locked_preview(
            plan_data,
            lock_scope=_load_json_mapping(args.lock_scope),
            timestamp=args.timestamp,
        )
        write_locked_preview_json(Path(args.output), preview)
        print(f"wrote locked preview with {len(preview.preview_writes)} preview writes to {args.output}")
        return 0
    if args.command == "promotion-execute":
        preview_data = _load_required_json_mapping(args.preview, "locked preview")
        receipt = build_execution_receipt(
            preview_data,
            execution_approval=_load_json_mapping(args.execution_approval),
            timestamp=args.timestamp,
        )
        write_execution_receipt_json(Path(args.output), receipt)
        print(f"wrote execution receipt with {len(receipt.executed_ops)} local receipt ops to {args.output}")
        return 0
    if args.command == "cortex-rollout":
        rollout = build_cortex_rollout(timestamp=args.timestamp)
        write_cortex_rollout_json(Path(args.output), rollout)
        print(f"wrote cortex rollout plan for {len(rollout.sisters)} sisters to {args.output}")
        return 0
    if args.command == "persistence-bundle":
        bundle = build_persistence_bundle(
            repo_root=Path(args.repo_root),
            vault_root=Path(args.vault),
            artifact_root=Path(args.artifact_root),
            interval_minutes=args.interval_minutes,
        )
        written = write_persistence_bundle(Path(args.output_dir), bundle)
        print(f"wrote CyBroCamp persistence bundle to {Path(args.output_dir)} ({len(written)} files)")
        return 0
    if args.command == "local-api-status":
        status = build_api_status(artifact_dir=Path(args.artifact_dir), timestamp=args.timestamp)
        if args.output:
            write_api_json_response(args.output, status)
            print(f"wrote local API status to {args.output}")
        else:
            print(json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.command == "local-api-query":
        response = build_query_response(
            artifact_dir=Path(args.artifact_dir),
            payload={"query": args.query, "top_k": args.top_k, "include_graph": not args.no_graph},
            timestamp=args.timestamp,
        )
        output = write_api_json_response(args.output, response)
        print(f"wrote local API query response to {output}")
        return 0
    if args.command == "local-api-bundle":
        bundle = build_api_bundle(
            repo_root=Path(args.repo_root),
            artifact_dir=Path(args.artifact_dir),
            host=args.host,
            port=args.port,
            auth_token_file=args.auth_token_file,
        )
        written = write_api_bundle(Path(args.output_dir), bundle)
        print(f"wrote CyBroCamp local API bundle to {Path(args.output_dir)} ({len(written)} files)")
        return 0
    if args.command == "local-api":
        run_local_api(artifact_dir=Path(args.artifact_dir), host=args.host, port=args.port, auth_token_file=args.auth_token_file)
        return 0
    parser.error("unsupported command")
    return 2


def _load_json_object(path: str | None) -> dict[str, str] | None:
    if path is None:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return {str(key): str(value) for key, value in data.items()}


def _load_json_list(path: str | None) -> list[dict[str, object]]:
    if path is None:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [data]
    if not isinstance(data, list):
        raise ValueError("expected JSON list or object")
    return [item for item in data if isinstance(item, dict)]


def _load_json_mapping(path: str | None) -> dict[str, object] | None:
    if path is None:
        return None
    return _load_required_json_mapping(path, "JSON object")


def _load_required_json_mapping(path: str, label: str) -> dict[str, object]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected {label} JSON object")
    return data


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
