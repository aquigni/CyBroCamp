from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .chunks import chunk_records_from_obsidian, write_chunk_manifest_jsonl
from .fact_cache import extract_fact_candidates, write_fact_cache_jsonl
from .graph_index import build_term_graph, write_term_graph_jsonl
from .manifest import manifest_records_from_obsidian, write_manifest_jsonl
from .search_index import search_terms, write_search_terms_jsonl

REBUILD_SCHEMA_VERSION = "cybrocamp.rebuild_run.v1"


@dataclass(frozen=True, slots=True)
class RebuildResult:
    output_dir: Path
    artifacts: dict[str, dict[str, object]]
    record_counts: dict[str, int]
    run_manifest_path: Path


def rebuild_all(
    vault_root: str | Path,
    output_dir: str | Path,
    *,
    epoch: str,
    timestamp: str,
    max_chars: int = 1200,
    max_terms_per_record: int = 12,
    source_label: str | None = None,
) -> RebuildResult:
    vault = Path(vault_root).resolve(strict=True)
    out = Path(output_dir).resolve(strict=False)
    if out == vault or vault in out.parents:
        raise ValueError("output_dir must be outside vault_root to keep canonical sources read-only")
    out.mkdir(parents=True, exist_ok=True)
    label = source_label or vault.name

    sources = list(manifest_records_from_obsidian(vault, epoch=epoch, created_at=timestamp))
    chunks = list(chunk_records_from_obsidian(vault, max_chars=max_chars, epoch=epoch, created_at=timestamp))
    terms = search_terms(chunks)
    graph = build_term_graph(terms, max_terms_per_record=max_terms_per_record)
    facts = extract_fact_candidates(terms, max_terms_per_record=min(max_terms_per_record, 12))

    paths = {
        "obsidian-manifest.jsonl": out / "obsidian-manifest.jsonl",
        "obsidian-chunks.jsonl": out / "obsidian-chunks.jsonl",
        "obsidian-search-terms.jsonl": out / "obsidian-search-terms.jsonl",
        "obsidian-term-graph.jsonl": out / "obsidian-term-graph.jsonl",
        "obsidian-fact-candidates.jsonl": out / "obsidian-fact-candidates.jsonl",
    }
    write_manifest_jsonl(paths["obsidian-manifest.jsonl"], sources)
    write_chunk_manifest_jsonl(paths["obsidian-chunks.jsonl"], chunks)
    write_search_terms_jsonl(paths["obsidian-search-terms.jsonl"], terms)
    write_term_graph_jsonl(paths["obsidian-term-graph.jsonl"], graph.edges)
    write_fact_cache_jsonl(paths["obsidian-fact-candidates.jsonl"], facts)

    record_counts = {
        "sources": len(sources),
        "chunks": len(chunks),
        "search_terms": len(terms),
        "term_edges": len(graph.edges),
        "fact_candidates": len(facts),
    }
    artifacts = {
        name: {
            "sha256": _file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for name, path in sorted(paths.items())
    }
    run_manifest = {
        "schema_version": REBUILD_SCHEMA_VERSION,
        "timestamp": timestamp,
        "epoch": epoch,
        "source_label": label,
        "parameters": {
            "max_chars": max_chars,
            "max_terms_per_record": max_terms_per_record,
        },
        "git_commit": _git_commit(Path(__file__).resolve().parents[2]),
        "record_counts": record_counts,
        "artifacts": artifacts,
    }
    run_manifest_path = out / "run-manifest.json"
    _write_json_atomic(run_manifest_path, run_manifest)
    return RebuildResult(output_dir=out, artifacts=artifacts, record_counts=record_counts, run_manifest_path=run_manifest_path)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None
