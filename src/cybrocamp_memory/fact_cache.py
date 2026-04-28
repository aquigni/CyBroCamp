from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

from .schema import AuthorityClass
from .search_index import SearchTermRecord, build_search_terms

FACT_CACHE_SCHEMA_VERSION = "cybrocamp.fact_cache.v1"


@dataclass(frozen=True, slots=True)
class FactCandidate:
    subject: str
    predicate: str
    object: str
    source_id: str
    source_uri: str
    chunk_id: str
    content_hash: str
    source_content_hash: str
    span_start: int
    span_end: int
    authority: AuthorityClass
    evidence_authority: AuthorityClass
    claims_user_approval: bool = False
    schema_version: str = FACT_CACHE_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["authority"] = self.authority.value
        data["evidence_authority"] = self.evidence_authority.value
        return data

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> "FactCandidate":
        return cls(
            subject=str(data["subject"]),
            predicate=str(data["predicate"]),
            object=str(data["object"]),
            source_id=str(data["source_id"]),
            source_uri=str(data["source_uri"]),
            chunk_id=str(data["chunk_id"]),
            content_hash=str(data["content_hash"]),
            source_content_hash=str(data["source_content_hash"]),
            span_start=int(data["span_start"]),
            span_end=int(data["span_end"]),
            authority=AuthorityClass(str(data["authority"])),
            evidence_authority=AuthorityClass(str(data["evidence_authority"])),
            claims_user_approval=bool(data.get("claims_user_approval", False)),
            schema_version=str(data.get("schema_version", FACT_CACHE_SCHEMA_VERSION)),
        )


def extract_fact_candidates(records: Iterable[SearchTermRecord], *, max_terms_per_record: int = 12) -> list[FactCandidate]:
    candidates: list[FactCandidate] = []
    for record in sorted(records, key=lambda item: (item.source_id, item.chunk_id)):
        terms = sorted(
            sorted({term for term in record.terms if _safe_fact_term(term)}, key=lambda term: (-len(term), term))[
                :max_terms_per_record
            ]
        )
        for subject, obj in combinations(terms, 2):
            candidates.append(
                FactCandidate(
                    subject=subject,
                    predicate="co_occurs_with",
                    object=obj,
                    source_id=record.source_id,
                    source_uri=record.source_uri,
                    chunk_id=record.chunk_id,
                    content_hash=record.content_hash,
                    source_content_hash=record.source_content_hash,
                    span_start=record.span_start,
                    span_end=record.span_end,
                    authority=AuthorityClass.DERIVED_SUMMARY,
                    evidence_authority=record.authority,
                    claims_user_approval=False,
                )
            )
    return sorted(candidates, key=lambda item: (item.subject, item.predicate, item.object, item.source_id, item.chunk_id))


def write_fact_cache_jsonl(path: str | Path, facts: Iterable[FactCandidate]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(facts, key=lambda item: (item.subject, item.predicate, item.object, item.source_id, item.chunk_id))
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for fact in ordered:
                json.dump(fact.to_json_dict(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_fact_cache_jsonl(path: str | Path) -> list[FactCandidate]:
    facts: list[FactCandidate] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                facts.append(FactCandidate.from_json_dict(json.loads(line)))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid fact cache line {line_number}") from exc
    return sorted(facts, key=lambda item: (item.subject, item.predicate, item.object, item.source_id, item.chunk_id))


def _safe_fact_term(term: str) -> bool:
    return build_search_terms(term) == [term]
