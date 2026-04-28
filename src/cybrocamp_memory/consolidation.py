from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from .fact_cache import FactCandidate
from .schema import AuthorityClass


@dataclass(frozen=True, slots=True)
class Contradiction:
    subject: str
    predicate: str
    objects: list[str]
    fact_ids: list[str]


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    fact: FactCandidate
    can_promote: bool
    reasons: list[str]


def detect_contradictions(facts: Sequence[FactCandidate]) -> list[Contradiction]:
    grouped: dict[tuple[str, str], dict[str, list[FactCandidate]]] = defaultdict(lambda: defaultdict(list))
    for fact in facts:
        grouped[(_norm(fact.subject), _norm(fact.predicate))][_norm(fact.object)].append(fact)
    contradictions: list[Contradiction] = []
    for (subject, predicate), by_object in grouped.items():
        if len(by_object) < 2:
            continue
        objects = sorted(by_object)
        fact_ids = sorted(fact.chunk_id for object_facts in by_object.values() for fact in object_facts)
        contradictions.append(Contradiction(subject=subject, predicate=predicate, objects=objects, fact_ids=fact_ids))
    return sorted(contradictions, key=lambda item: (item.subject, item.predicate))


def decide_promotion(
    fact: FactCandidate,
    contradictions: Sequence[Contradiction],
    *,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
) -> PromotionDecision:
    reasons: list[str] = []
    if fact.authority is not AuthorityClass.USER_DIRECT:
        reasons.append("not_user_direct_authority")
    if fact.evidence_authority is not AuthorityClass.USER_DIRECT:
        reasons.append("not_user_direct_evidence")
    if current_source_hashes is not None and current_source_hashes.get(fact.source_id) != fact.source_content_hash:
        reasons.append("stale_source_hash")
    if current_chunk_hashes is not None and current_chunk_hashes.get(fact.chunk_id) != fact.content_hash:
        reasons.append("stale_chunk_hash")
    if _has_contradiction(fact, contradictions):
        reasons.append("contradiction_present")
    return PromotionDecision(fact=fact, can_promote=not reasons, reasons=reasons)


def _has_contradiction(fact: FactCandidate, contradictions: Sequence[Contradiction]) -> bool:
    subject = _norm(fact.subject)
    predicate = _norm(fact.predicate)
    return any(item.subject == subject and item.predicate == predicate for item in contradictions)


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())
