from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .schema import AuthorityClass, EvidenceSpan, RecallItem, RecallPacket
from .search_index import SearchTermRecord, build_search_terms, search_terms_from_obsidian

TERM_GRAPH_SCHEMA_VERSION = "cybrocamp.term_graph.v1"


@dataclass(frozen=True, slots=True)
class EdgeEvidence:
    source_id: str
    source_uri: str
    chunk_id: str
    chunk_index: int
    content_hash: str
    source_content_hash: str
    span_start: int
    span_end: int
    authority: AuthorityClass

    @classmethod
    def from_search_record(cls, record: SearchTermRecord) -> "EdgeEvidence":
        return cls(
            source_id=record.source_id,
            source_uri=record.source_uri,
            chunk_id=record.chunk_id,
            chunk_index=record.chunk_index,
            content_hash=record.content_hash,
            source_content_hash=record.source_content_hash,
            span_start=record.span_start,
            span_end=record.span_end,
            authority=record.authority,
        )

    def to_json_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["authority"] = self.authority.value
        return data

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> "EdgeEvidence":
        return cls(
            source_id=str(data["source_id"]),
            source_uri=str(data["source_uri"]),
            chunk_id=str(data["chunk_id"]),
            chunk_index=int(data["chunk_index"]),
            content_hash=str(data["content_hash"]),
            source_content_hash=str(data["source_content_hash"]),
            span_start=int(data["span_start"]),
            span_end=int(data["span_end"]),
            authority=AuthorityClass(str(data["authority"])),
        )


@dataclass(frozen=True, slots=True)
class TermEdgeRecord:
    term_a: str
    term_b: str
    evidence: list[EdgeEvidence]
    schema_version: str = TERM_GRAPH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.term_a > self.term_b:
            raise ValueError("term edge terms must be sorted")
        if self.term_a == self.term_b:
            raise ValueError("term edge requires distinct terms")
        if not self.evidence:
            raise ValueError("term edge requires evidence")

    @property
    def support_count(self) -> int:
        return len({item.chunk_id for item in self.evidence})

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "term_a": self.term_a,
            "term_b": self.term_b,
            "support_count": self.support_count,
            "evidence": [item.to_json_dict() for item in self.evidence],
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> "TermEdgeRecord":
        return cls(
            term_a=str(data["term_a"]),
            term_b=str(data["term_b"]),
            evidence=[EdgeEvidence.from_json_dict(item) for item in data["evidence"]],
            schema_version=str(data.get("schema_version", TERM_GRAPH_SCHEMA_VERSION)),
        )


@dataclass(frozen=True, slots=True)
class TermGraph:
    edges: list[TermEdgeRecord]

    def edge_for(self, left: str, right: str) -> TermEdgeRecord | None:
        a, b = sorted((left, right))
        for edge in self.edges:
            if edge.term_a == a and edge.term_b == b:
                return edge
        return None

    def neighbors(self, term: str) -> list[tuple[str, TermEdgeRecord]]:
        result: list[tuple[str, TermEdgeRecord]] = []
        for edge in self.edges:
            if edge.term_a == term:
                result.append((edge.term_b, edge))
            elif edge.term_b == term:
                result.append((edge.term_a, edge))
        return sorted(result, key=lambda item: (item[0], -item[1].support_count, item[1].term_a, item[1].term_b))


def build_term_graph(records: Iterable[SearchTermRecord], *, max_terms_per_record: int = 24) -> TermGraph:
    evidence_by_pair: dict[tuple[str, str], dict[str, EdgeEvidence]] = defaultdict(dict)
    for record in sorted(records, key=lambda r: (r.source_id, r.chunk_id)):
        # Defensive gate: Stage 5 accepts sanitized term records only; it never uses previews/raw text.
        unique_terms = {term for term in record.terms if term in build_search_terms(term)}
        terms = sorted(sorted(unique_terms, key=lambda term: (-len(term), term))[:max_terms_per_record])
        for left, right in combinations(terms, 2):
            evidence_by_pair[(left, right)][record.chunk_id] = EdgeEvidence.from_search_record(record)
    edges = [
        TermEdgeRecord(
            term_a=pair[0],
            term_b=pair[1],
            evidence=sorted(items.values(), key=lambda item: (item.source_id, item.chunk_id)),
        )
        for pair, items in evidence_by_pair.items()
    ]
    edges.sort(key=lambda edge: (edge.term_a, edge.term_b))
    return TermGraph(edges=edges)


def term_graph_from_obsidian(
    vault_root: str | Path,
    *,
    max_chars: int = 1200,
    max_terms_per_record: int = 24,
    epoch: str = "obsidian-scan-v1",
    created_at: str = "1970-01-01T00:00:00Z",
) -> TermGraph:
    return build_term_graph(
        search_terms_from_obsidian(vault_root, max_chars=max_chars, epoch=epoch, created_at=created_at),
        max_terms_per_record=max_terms_per_record,
    )


def write_term_graph_jsonl(path: str | Path, edges: Iterable[TermEdgeRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    unique = {(edge.term_a, edge.term_b): edge for edge in edges}
    ordered = [unique[key] for key in sorted(unique)]
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for edge in ordered:
                json.dump(edge.to_json_dict(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_term_graph_jsonl(path: str | Path) -> TermGraph:
    edges: list[TermEdgeRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                edges.append(TermEdgeRecord.from_json_dict(json.loads(line)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid term graph line {line_number}") from exc
    return TermGraph(edges=sorted(edges, key=lambda edge: (edge.term_a, edge.term_b)))


def recall_from_term_graph(
    graph: TermGraph,
    query: str,
    *,
    timestamp: str,
    top_k: int = 5,
    max_depth: int = 2,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
    include_stale: bool = True,
) -> RecallPacket:
    if top_k < 1 or max_depth < 1:
        return RecallPacket(query=query, items=[])
    query_terms = build_search_terms(query)
    paths: list[tuple[list[str], list[TermEdgeRecord], int, list[str]]] = []
    seen_paths: set[tuple[str, ...]] = set()
    for query_term in query_terms:
        queue = deque([(query_term, [query_term], [])])
        while queue:
            current, term_path, edge_path = queue.popleft()
            if edge_path:
                stale_flags = _stale_flags_for_edges(edge_path, current_source_hashes, current_chunk_hashes)
                if not stale_flags or include_stale:
                    key = tuple(term_path)
                    if key not in seen_paths:
                        seen_paths.add(key)
                        paths.append((term_path, edge_path, _path_score(edge_path, query_terms, term_path), stale_flags))
            if len(edge_path) >= max_depth:
                continue
            for neighbor, edge in graph.neighbors(current):
                if neighbor in term_path:
                    continue
                queue.append((neighbor, [*term_path, neighbor], [*edge_path, edge]))
    paths.sort(key=lambda item: (-item[2], len(item[0]), "->".join(item[0])))
    items: list[RecallItem] = []
    for term_path, edge_path, _score, stale_flags in paths[:top_k]:
        evidence = _first_evidence(edge_path)
        items.append(
            RecallItem(
                text=f"[GRAPH_RECALL:{'->'.join(term_path)}]",
                authority=AuthorityClass.DERIVED_SUMMARY,
                evidence=EvidenceSpan(
                    source_uri=evidence.source_uri,
                    start=evidence.span_start,
                    end=evidence.span_end,
                    content_hash=evidence.content_hash,
                    source_id=evidence.source_id,
                    chunk_id=evidence.chunk_id,
                    authority=evidence.authority,
                    quarantine_flags=[],
                    source_content_hash=evidence.source_content_hash,
                    stale_flags=list(stale_flags),
                ),
                timestamp=timestamp,
                claims_user_approval=False,
            )
        )
    return RecallPacket(query=query, items=items)


def _path_score(edges: Sequence[TermEdgeRecord], query_terms: Sequence[str], term_path: Sequence[str]) -> int:
    query_overlap = len(set(query_terms).intersection(term_path))
    return (query_overlap * 1000) + sum(edge.support_count for edge in edges)


def _first_evidence(edges: Sequence[TermEdgeRecord]) -> EdgeEvidence:
    candidates = [evidence for edge in edges for evidence in edge.evidence]
    return sorted(candidates, key=lambda item: (item.source_id, item.chunk_id))[0]


def _stale_flags_for_edges(
    edges: Sequence[TermEdgeRecord],
    current_source_hashes: Mapping[str, str] | None,
    current_chunk_hashes: Mapping[str, str] | None,
) -> list[str]:
    flags: set[str] = set()
    for edge in edges:
        for evidence in edge.evidence:
            if current_source_hashes is not None and current_source_hashes.get(evidence.source_id) != evidence.source_content_hash:
                flags.add("stale_source_hash")
            if current_chunk_hashes is not None and current_chunk_hashes.get(evidence.chunk_id) != evidence.content_hash:
                flags.add("stale_chunk_hash")
    return sorted(flags)
