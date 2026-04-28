from __future__ import annotations

from cybrocamp_memory.chunks import ChunkRecord
from cybrocamp_memory.manifest import SourceRecord
from cybrocamp_memory.retrieval import (
    lexical_search,
    recall_query,
    redact_query,
    stale_flags_for_chunk,
)
from cybrocamp_memory.schema import AuthorityClass


def _source(source_id: str = "source-1", content_hash: str = "sha256:source") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        uri=f"obsidian://{source_id}.md",
        authority=AuthorityClass.CANONICAL_VAULT,
        epoch="fixture",
        content_hash=content_hash,
        created_at="2026-04-29T00:00:00Z",
    )


def _chunk(
    text: str,
    *,
    source_id: str = "source-1",
    chunk_id: str | None = None,
    quarantine_flags: list[str] | None = None,
    source_hash: str = "sha256:source",
    content_hash: str | None = None,
) -> ChunkRecord:
    source = _source(source_id, source_hash)
    record = ChunkRecord.from_text(source, 0, text, 0, len(text.encode("utf-8")))
    return ChunkRecord(
        source_id=record.source_id,
        source_uri=record.source_uri,
        chunk_id=chunk_id or record.chunk_id,
        chunk_index=record.chunk_index,
        content_hash=content_hash or record.content_hash,
        source_content_hash=record.source_content_hash,
        span_start=record.span_start,
        span_end=record.span_end,
        text=record.text,
        text_preview="[REDACTED:secret]" if quarantine_flags else record.text_preview,
        authority=record.authority,
        quarantine_flags=quarantine_flags or record.quarantine_flags,
    )


def test_lexical_search_excludes_quarantined_chunks():
    clean = _chunk("CyBroCamp source manifest architecture")
    dirty = _chunk("unique-secret-token CyBroCamp", source_id="source-2", quarantine_flags=["secret"])

    hits = lexical_search([dirty, clean], "unique-secret-token CyBroCamp", top_k=10)

    assert [hit.chunk.chunk_id for hit in hits] == [clean.chunk_id]
    assert "unique-secret-token" not in hits[0].chunk.text_preview


def test_lexical_search_ranking_is_deterministic_with_stable_tie_break():
    a = _chunk("alpha beta", source_id="b-source", chunk_id="b-chunk")
    b = _chunk("alpha beta", source_id="a-source", chunk_id="a-chunk")

    first = lexical_search([a, b], "alpha beta", top_k=10)
    second = lexical_search([b, a], "alpha beta", top_k=10)

    assert [hit.chunk.chunk_id for hit in first] == ["a-chunk", "b-chunk"]
    assert [hit.chunk.chunk_id for hit in second] == ["a-chunk", "b-chunk"]


def test_recall_query_returns_complete_evidence_schema():
    chunk = _chunk("hippocampus cortex evidence")

    packet = recall_query([chunk], "hippocampus", timestamp="2026-04-29T00:00:00Z")

    assert packet.policy_warnings == []
    evidence = packet.items[0].evidence
    assert evidence.source_id == chunk.source_id
    assert evidence.chunk_id == chunk.chunk_id
    assert evidence.content_hash == chunk.content_hash
    assert evidence.source_content_hash == chunk.source_content_hash
    assert evidence.authority is AuthorityClass.CANONICAL_VAULT
    assert evidence.stale_flags == []


def test_stale_source_hash_marks_evidence_stale():
    chunk = _chunk("hippocampus cortex evidence", source_hash="sha256:old-source")

    flags = stale_flags_for_chunk(chunk, current_source_hashes={chunk.source_id: "sha256:new-source"})
    packet = recall_query(
        [chunk],
        "hippocampus",
        timestamp="2026-04-29T00:00:00Z",
        current_source_hashes={chunk.source_id: "sha256:new-source"},
    )

    assert flags == ["stale_source_hash"]
    assert "stale_evidence" in packet.policy_warnings
    assert packet.items[0].evidence.stale_flags == ["stale_source_hash"]


def test_stale_chunk_hash_marks_evidence_stale():
    chunk = _chunk("hippocampus cortex evidence", content_hash="sha256:old-chunk")

    flags = stale_flags_for_chunk(chunk, current_chunk_hashes={chunk.chunk_id: "sha256:new-chunk"})

    assert flags == ["stale_chunk_hash"]


def test_recall_query_does_not_return_only_stale_hits_as_valid():
    chunk = _chunk("only stale match", source_hash="sha256:old")

    packet = recall_query(
        [chunk],
        "stale match",
        timestamp="2026-04-29T00:00:00Z",
        current_source_hashes={chunk.source_id: "sha256:new"},
        include_stale=False,
    )

    assert packet.items == []
    assert "no_valid_hits" in packet.policy_warnings


def test_query_redaction_removes_secret_like_tokens():
    redacted = redact_query("find API_KEY=sk-test-secret-token in notes")

    assert "sk-test-secret-token" not in redacted
    assert redacted == "find [REDACTED] in notes"
