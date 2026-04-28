from __future__ import annotations

from cybrocamp_memory.chunks import ChunkRecord
from cybrocamp_memory.eval import EvaluationCase, run_local_eval
from cybrocamp_memory.manifest import SourceRecord
from cybrocamp_memory.schema import AuthorityClass


def _chunk(text: str, source_id: str = "source-1") -> ChunkRecord:
    source = SourceRecord(
        source_id=source_id,
        uri=f"obsidian://{source_id}.md",
        authority=AuthorityClass.CANONICAL_VAULT,
        epoch="fixture",
        content_hash="sha256:source",
        created_at="2026-04-29T00:00:00Z",
    )
    return ChunkRecord.from_text(source, 0, text, 0, len(text.encode("utf-8")))


def test_local_eval_records_ids_scores_hashes_not_raw_text():
    chunks = [_chunk("CyBroCamp hippocampus evidence")]
    cases = [EvaluationCase(name="hippo", query="hippocampus", expected_terms=["CyBroCamp"])]

    result = run_local_eval(cases, chunks, timestamp="2026-04-29T00:00:00Z")

    assert result["cases"][0]["hit_count"] == 1
    assert result["cases"][0]["hits"][0]["chunk_id"] == chunks[0].chunk_id
    assert "CyBroCamp hippocampus evidence" not in str(result)
    assert "text" not in result["cases"][0]["hits"][0]
