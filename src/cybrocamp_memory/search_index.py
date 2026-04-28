from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .chunks import ChunkRecord, chunk_records_from_obsidian
from .schema import AuthorityClass, EvidenceSpan, RecallItem, RecallPacket


SEARCH_TERM_SCHEMA_VERSION = "cybrocamp.search_terms.v1"

_DROP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$"),
    re.compile(r"(?i)^https?://"),
    re.compile(r"(?i)^(api[_-]?key|secret|token|password|passwd|cookie)$"),
    re.compile(r"(?i)^(sk|ghp|xox[baprs])[-_a-z0-9]+$"),
    re.compile(r"(?i)^[a-f0-9]{16,}$"),
    re.compile(r"(?i)^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"),
    re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$"),
)


@dataclass(frozen=True, slots=True)
class SearchTermRecord:
    source_id: str
    source_uri: str
    chunk_id: str
    chunk_index: int
    content_hash: str
    source_content_hash: str
    span_start: int
    span_end: int
    text_preview: str
    authority: AuthorityClass
    terms: list[str]
    schema_version: str = SEARCH_TERM_SCHEMA_VERSION

    @classmethod
    def from_chunk(cls, chunk: ChunkRecord) -> "SearchTermRecord":
        if chunk.quarantine_flags:
            raise ValueError("quarantined chunks cannot be indexed")
        return cls(
            source_id=chunk.source_id,
            source_uri=chunk.source_uri,
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.chunk_index,
            content_hash=chunk.content_hash,
            source_content_hash=chunk.source_content_hash,
            span_start=chunk.span_start,
            span_end=chunk.span_end,
            text_preview=chunk.text_preview,
            authority=chunk.authority,
            terms=build_search_terms(chunk.text),
        )

    def to_json_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["authority"] = self.authority.value
        data.pop("text_preview", None)
        return data

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> "SearchTermRecord":
        return cls(
            source_id=str(data["source_id"]),
            source_uri=str(data["source_uri"]),
            chunk_id=str(data["chunk_id"]),
            chunk_index=int(data["chunk_index"]),
            content_hash=str(data["content_hash"]),
            source_content_hash=str(data["source_content_hash"]),
            span_start=int(data["span_start"]),
            span_end=int(data["span_end"]),
            text_preview=str(data.get("text_preview", "")),
            authority=AuthorityClass(str(data["authority"])),
            terms=[str(term) for term in data["terms"]],
            schema_version=str(data.get("schema_version", SEARCH_TERM_SCHEMA_VERSION)),
        )


def build_search_terms(text: str) -> list[str]:
    terms: set[str] = set()
    for raw in re.findall(r"https?://\S+|[\w@./:+%-]+", text, flags=re.UNICODE):
        token = raw.strip("`'\"()[]{}<>,.;!?“”‘’").lower()
        if not token or len(token) < 2 or len(token) > 32:
            continue
        if any(pattern.match(token) for pattern in _DROP_PATTERNS):
            continue
        if "@" in token or "://" in token:
            continue
        terms.add(token)
    return sorted(terms)


def search_terms(chunks: Iterable[ChunkRecord]) -> list[SearchTermRecord]:
    records = [SearchTermRecord.from_chunk(chunk) for chunk in chunks if not chunk.quarantine_flags]
    return sorted(records, key=lambda record: (record.source_id, record.chunk_id))


def search_terms_from_obsidian(
    vault_root: str | Path,
    *,
    max_chars: int = 1200,
    epoch: str = "obsidian-scan-v1",
    created_at: str = "1970-01-01T00:00:00Z",
) -> list[SearchTermRecord]:
    chunks = chunk_records_from_obsidian(vault_root, max_chars=max_chars, epoch=epoch, created_at=created_at)
    return search_terms(chunks)


def write_search_terms_jsonl(path: str | Path, records: Iterable[SearchTermRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    unique = {record.chunk_id: record for record in records}
    ordered = [unique[key] for key in sorted(unique)]
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in ordered:
                json.dump(record.to_json_dict(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_search_terms_jsonl(path: str | Path) -> list[SearchTermRecord]:
    records: list[SearchTermRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(SearchTermRecord.from_json_dict(json.loads(line)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid search terms line {line_number}") from exc
    return records


def recall_from_search_terms(
    records: Sequence[SearchTermRecord],
    query: str,
    *,
    timestamp: str,
    top_k: int = 5,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
    include_stale: bool = True,
) -> RecallPacket:
    query_terms = build_search_terms(query)
    hits = []
    for record in records:
        score = _score(record, query_terms)
        if score == 0:
            continue
        stale_flags = _stale_flags(record, current_source_hashes, current_chunk_hashes)
        if stale_flags and not include_stale:
            continue
        hits.append((record, score, stale_flags))
    hits.sort(key=lambda hit: (-hit[1], hit[0].authority.value, hit[0].source_id, hit[0].chunk_id))
    items = [
        RecallItem(
            text=record.text_preview or f"[INDEXED_RECALL:{record.source_uri}]",
            authority=record.authority,
            evidence=EvidenceSpan(
                source_uri=record.source_uri,
                start=record.span_start,
                end=record.span_end,
                content_hash=record.content_hash,
                source_id=record.source_id,
                chunk_id=record.chunk_id,
                authority=record.authority,
                quarantine_flags=[],
                source_content_hash=record.source_content_hash,
                stale_flags=list(stale_flags),
            ),
            timestamp=timestamp,
        )
        for record, _score_value, stale_flags in hits[:top_k]
    ]
    return RecallPacket(query=query, items=items)


def _score(record: SearchTermRecord, query_terms: Sequence[str]) -> int:
    term_counts = {term: record.terms.count(term) for term in set(record.terms)}
    return sum(term_counts.get(term, 0) for term in query_terms)


def _stale_flags(
    record: SearchTermRecord,
    current_source_hashes: Mapping[str, str] | None,
    current_chunk_hashes: Mapping[str, str] | None,
) -> list[str]:
    flags: list[str] = []
    if current_source_hashes is not None and current_source_hashes.get(record.source_id) != record.source_content_hash:
        flags.append("stale_source_hash")
    if current_chunk_hashes is not None and current_chunk_hashes.get(record.chunk_id) != record.content_hash:
        flags.append("stale_chunk_hash")
    return flags
