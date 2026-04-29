from __future__ import annotations

import json

from cybrocamp_memory.chunks import ChunkRecord
from cybrocamp_memory.manifest import SourceRecord
from cybrocamp_memory.retrieval import lexical_search
from cybrocamp_memory.schema import AuthorityClass
from cybrocamp_memory.search_index import (
    SearchTermRecord,
    build_search_terms,
    recall_from_search_terms,
    search_terms,
    write_search_terms_jsonl,
)


def _source(source_id: str = "source-1") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        uri=f"obsidian://{source_id}.md",
        authority=AuthorityClass.CANONICAL_VAULT,
        epoch="fixture",
        content_hash="sha256:source",
        created_at="2026-04-29T00:00:00Z",
    )


def _chunk(text: str, *, source_id: str = "source-1", quarantine_flags: list[str] | None = None) -> ChunkRecord:
    record = ChunkRecord.from_text(_source(source_id), 0, text, 0, len(text.encode("utf-8")))
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


def test_sanitizer_drops_sensitive_tokens():
    terms = build_search_terms(
        "Contact admin@example.com https://example.com secret=fixture 550e8400-e29b-41d4-a716-446655440000 normal survival"
    )

    assert "normal" in terms
    assert "survival" in terms
    assert "admin" not in terms
    assert "example" not in terms
    assert "sk" not in terms
    assert "550e8400" not in terms


def test_quarantine_before_indexing_excludes_unique_token():
    dirty = _chunk("survival_economics_canary should not be indexed", quarantine_flags=["secret"])

    records = search_terms([dirty])

    assert records == []


def test_survival_economics_regression_beyond_preview():
    long_prefix = "irrelevant " * 40
    chunk = _chunk(long_prefix + " survival economics financial substrate CyBroSwarm")

    preview_hits = lexical_search([chunk], "survival economics financial substrate CyBroSwarm", top_k=3)
    index_hits = recall_from_search_terms(
        search_terms([chunk]),
        "survival economics financial substrate CyBroSwarm",
        timestamp="2026-04-29T00:00:00Z",
    )

    assert preview_hits == []
    assert index_hits.items
    assert index_hits.items[0].evidence.chunk_id == chunk.chunk_id


def test_search_index_jsonl_contains_terms_not_raw_text(tmp_path):
    chunk = _chunk("alpha beta gamma complete sentence")
    output = tmp_path / "search_terms.jsonl"

    write_search_terms_jsonl(output, search_terms([chunk]))
    raw = output.read_text(encoding="utf-8")
    decoded = json.loads(raw.splitlines()[0])

    assert "complete sentence" not in raw
    assert "text" not in decoded
    assert decoded["terms"] == ["alpha", "beta", "complete", "gamma", "sentence"]


def test_search_terms_ranking_is_deterministic():
    a = SearchTermRecord.from_chunk(_chunk("alpha beta", source_id="b-source"))
    b = SearchTermRecord.from_chunk(_chunk("alpha beta", source_id="a-source"))

    first = recall_from_search_terms([a, b], "alpha beta", timestamp="2026-04-29T00:00:00Z")
    second = recall_from_search_terms([b, a], "alpha beta", timestamp="2026-04-29T00:00:00Z")

    assert [item.evidence.source_id for item in first.items] == ["a-source", "b-source"]
    assert [item.evidence.source_id for item in second.items] == ["a-source", "b-source"]


def test_stale_hash_candidate_rejected_from_search_terms():
    chunk = _chunk("survival economics")
    records = search_terms([chunk])

    packet = recall_from_search_terms(
        records,
        "survival economics",
        timestamp="2026-04-29T00:00:00Z",
        current_source_hashes={chunk.source_id: "sha256:new"},
        include_stale=False,
    )

    assert packet.items == []
    assert "no_valid_hits" in packet.policy_warnings
