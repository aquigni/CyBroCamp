from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .chunks import ChunkRecord
from .retrieval import lexical_search, redact_query


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    name: str
    query: str
    expected_terms: list[str]


def run_local_eval(
    cases: Sequence[EvaluationCase],
    chunks: Sequence[ChunkRecord],
    *,
    timestamp: str,
    top_k: int = 5,
) -> dict[str, object]:
    return {
        "schema_version": "cybrocamp.local_eval.v1",
        "timestamp": timestamp,
        "cases": [_case_result(case, chunks, top_k=top_k) for case in cases],
    }


def _case_result(case: EvaluationCase, chunks: Sequence[ChunkRecord], *, top_k: int) -> dict[str, object]:
    hits = lexical_search(chunks, case.query, top_k=top_k, include_stale=False)
    return {
        "name": case.name,
        "query": redact_query(case.query),
        "expected_terms": [redact_query(term) for term in case.expected_terms],
        "hit_count": len(hits),
        "hits": [
            {
                "source_id": hit.chunk.source_id,
                "source_uri": hit.chunk.source_uri,
                "chunk_id": hit.chunk.chunk_id,
                "score": hit.score,
                "content_hash": hit.chunk.content_hash,
                "source_content_hash": hit.chunk.source_content_hash,
                "authority": hit.chunk.authority.value,
                "quarantine_flags": list(hit.chunk.quarantine_flags),
                "stale_flags": list(hit.stale_flags),
            }
            for hit in hits
        ],
    }
