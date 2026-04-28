from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .chunks import ChunkRecord
from .schema import EvidenceSpan, RecallItem, RecallPacket


_SECRET_QUERY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|cookie)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\b(?:sk|ghp|xox[baprs])-[-A-Za-z0-9_]{8,}\b"),
)


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk: ChunkRecord
    score: int
    stale_flags: list[str]


def lexical_search(
    chunks: Sequence[ChunkRecord],
    query: str,
    *,
    top_k: int = 5,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
    include_stale: bool = True,
) -> list[RetrievalHit]:
    if top_k < 1:
        return []
    tokens = _tokens(query)
    if not tokens:
        return []
    hits: list[RetrievalHit] = []
    for chunk in chunks:
        if chunk.quarantine_flags:
            continue
        score = _score(chunk, tokens)
        if score == 0:
            continue
        stale_flags = stale_flags_for_chunk(
            chunk,
            current_source_hashes=current_source_hashes,
            current_chunk_hashes=current_chunk_hashes,
        )
        if stale_flags and not include_stale:
            continue
        hits.append(RetrievalHit(chunk=chunk, score=score, stale_flags=stale_flags))
    return sorted(
        hits,
        key=lambda hit: (-hit.score, hit.chunk.authority.value, hit.chunk.source_id, hit.chunk.chunk_id),
    )[:top_k]


def recall_query(
    chunks: Sequence[ChunkRecord],
    query: str,
    *,
    timestamp: str,
    top_k: int = 5,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
    include_stale: bool = True,
) -> RecallPacket:
    hits = lexical_search(
        chunks,
        query,
        top_k=top_k,
        current_source_hashes=current_source_hashes,
        current_chunk_hashes=current_chunk_hashes,
        include_stale=include_stale,
    )
    items = [
        RecallItem(
            text=hit.chunk.text_preview,
            authority=hit.chunk.authority,
            evidence=_evidence_for_hit(hit),
            timestamp=timestamp,
        )
        for hit in hits
    ]
    return RecallPacket(query=redact_query(query), items=items)


def stale_flags_for_chunk(
    chunk: ChunkRecord,
    *,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
) -> list[str]:
    flags: list[str] = []
    if current_source_hashes is not None:
        current_source_hash = current_source_hashes.get(chunk.source_id)
        if current_source_hash is None or current_source_hash != chunk.source_content_hash:
            flags.append("stale_source_hash")
    if current_chunk_hashes is not None:
        current_chunk_hash = current_chunk_hashes.get(chunk.chunk_id)
        if current_chunk_hash is None or current_chunk_hash != chunk.content_hash:
            flags.append("stale_chunk_hash")
    return flags


def redact_query(query: str) -> str:
    redacted = query
    for pattern in _SECRET_QUERY_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _evidence_for_hit(hit: RetrievalHit) -> EvidenceSpan:
    chunk = hit.chunk
    return EvidenceSpan(
        source_uri=chunk.source_uri,
        start=chunk.span_start,
        end=chunk.span_end,
        content_hash=chunk.content_hash,
        source_id=chunk.source_id,
        chunk_id=chunk.chunk_id,
        authority=chunk.authority,
        quarantine_flags=list(chunk.quarantine_flags),
        source_content_hash=chunk.source_content_hash,
        stale_flags=list(hit.stale_flags),
    )


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[\wА-Яа-яёЁ]+", text)]


def _score(chunk: ChunkRecord, query_tokens: Sequence[str]) -> int:
    haystack = f"{chunk.text_preview} {chunk.source_uri}".lower()
    return sum(haystack.count(token) for token in query_tokens)
