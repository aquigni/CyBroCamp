from __future__ import annotations

import json

from cybrocamp_memory.chunks import ChunkRecord
from cybrocamp_memory.graph_index import (
    build_term_graph,
    recall_from_term_graph,
    write_term_graph_jsonl,
)
from cybrocamp_memory.manifest import SourceRecord
from cybrocamp_memory.schema import AuthorityClass
from cybrocamp_memory.search_index import SearchTermRecord, search_terms


def _source(source_id: str = "source-1", authority: AuthorityClass = AuthorityClass.CANONICAL_VAULT) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        uri=f"obsidian://{source_id}.md",
        authority=authority,
        epoch="fixture",
        content_hash=f"sha256:{source_id}",
        created_at="2026-04-29T00:00:00Z",
    )


def _chunk(
    text: str,
    *,
    source_id: str = "source-1",
    authority: AuthorityClass = AuthorityClass.CANONICAL_VAULT,
    quarantine_flags: list[str] | None = None,
) -> ChunkRecord:
    record = ChunkRecord.from_text(_source(source_id, authority), 0, text, 0, len(text.encode("utf-8")))
    if not quarantine_flags:
        return record
    return ChunkRecord(
        source_id=record.source_id,
        source_uri=record.source_uri,
        chunk_id=record.chunk_id,
        chunk_index=record.chunk_index,
        content_hash=record.content_hash,
        source_content_hash=record.source_content_hash,
        span_start=record.span_start,
        span_end=record.span_end,
        text=record.text,
        text_preview="[REDACTED:secret]",
        authority=record.authority,
        quarantine_flags=quarantine_flags,
    )


def _records(*chunks: ChunkRecord) -> list[SearchTermRecord]:
    return search_terms(chunks)


def test_graph_edges_are_evidence_backed_and_omit_raw_text(tmp_path):
    chunk = _chunk("hippocampus cortex provenance")
    graph = build_term_graph(_records(chunk))
    output = tmp_path / "graph.jsonl"

    write_term_graph_jsonl(output, graph.edges)
    raw = output.read_text(encoding="utf-8")
    decoded = [json.loads(line) for line in raw.splitlines()]

    assert graph.edge_for("hippocampus", "cortex") is not None
    assert "hippocampus cortex provenance" not in raw
    assert "text" not in decoded[0]
    assert decoded[0]["evidence"][0]["chunk_id"] == chunk.chunk_id
    assert decoded[0]["evidence"][0]["authority"] == "canonical_vault"


def test_quarantined_records_do_not_enter_graph_paths():
    dirty = _chunk("alpha forbidden_canary", quarantine_flags=["secret"])
    clean = _chunk("alpha beta", source_id="clean")

    graph = build_term_graph(_records(dirty, clean))
    packet = recall_from_term_graph(graph, "forbidden_canary", timestamp="2026-04-29T00:00:00Z")

    assert graph.edge_for("alpha", "forbidden_canary") is None
    assert packet.items == []
    assert "no_valid_hits" in packet.policy_warnings


def test_two_hop_recall_explains_path_without_direct_evidence_claim():
    left = _chunk("alpha bridge", source_id="left")
    right = _chunk("bridge gamma", source_id="right")
    graph = build_term_graph(_records(left, right))

    packet = recall_from_term_graph(graph, "alpha", timestamp="2026-04-29T00:00:00Z", top_k=5, max_depth=2)

    texts = [item.text for item in packet.items]
    assert "[GRAPH_RECALL:alpha->bridge->gamma]" in texts
    gamma = next(item for item in packet.items if item.text == "[GRAPH_RECALL:alpha->bridge->gamma]")
    assert gamma.authority is AuthorityClass.DERIVED_SUMMARY
    assert gamma.evidence.chunk_id in {left.chunk_id, right.chunk_id}


def test_graph_recall_is_deterministic_for_shuffled_records():
    a = _chunk("alpha bridge", source_id="b-source")
    b = _chunk("alpha bridge", source_id="a-source")
    first_graph = build_term_graph(_records(a, b))
    second_graph = build_term_graph(list(reversed(_records(a, b))))

    first = recall_from_term_graph(first_graph, "alpha", timestamp="2026-04-29T00:00:00Z")
    second = recall_from_term_graph(second_graph, "alpha", timestamp="2026-04-29T00:00:00Z")

    assert [item.text for item in first.items] == [item.text for item in second.items]
    assert [item.evidence.source_id for item in first.items] == [item.evidence.source_id for item in second.items]


def test_stale_graph_edges_can_be_excluded():
    chunk = _chunk("alpha bridge", source_id="stale")
    graph = build_term_graph(_records(chunk))

    packet = recall_from_term_graph(
        graph,
        "alpha",
        timestamp="2026-04-29T00:00:00Z",
        current_source_hashes={chunk.source_id: "sha256:new"},
        include_stale=False,
    )

    assert packet.items == []
    assert "no_valid_hits" in packet.policy_warnings


def test_authority_is_not_promoted_across_association_path():
    low = _chunk("alpha bridge", source_id="low", authority=AuthorityClass.A2A_PEER_CLAIM)
    high = _chunk("bridge approved", source_id="high", authority=AuthorityClass.USER_DIRECT)
    graph = build_term_graph(_records(low, high))

    packet = recall_from_term_graph(graph, "alpha", timestamp="2026-04-29T00:00:00Z", max_depth=2)

    approved = next(item for item in packet.items if item.text == "[GRAPH_RECALL:alpha->bridge->approved]")
    assert approved.authority is AuthorityClass.DERIVED_SUMMARY
    assert approved.claims_user_approval is False
