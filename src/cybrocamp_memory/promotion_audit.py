from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .consolidation import Contradiction, detect_contradictions
from .fact_cache import FactCandidate
from .schema import AuthorityClass

PROMOTION_AUDIT_SCHEMA_VERSION = "cybrocamp.promotion_audit.v1"
_DECISIONS = {"blocked", "needs_h0st_approval", "promotable_candidate"}
_SECRET_TERM_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class PromotionAuditItem:
    subject: str
    predicate: str
    object: str
    decision: str
    reasons: list[str]
    evidence_bundle: dict[str, object]
    authority_chain: dict[str, str]
    requires_h0st_approval: bool
    mempalace_comparison: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.decision not in _DECISIONS:
            raise ValueError("invalid promotion audit decision")

    def to_json_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "decision": self.decision,
            "reasons": list(self.reasons),
            "evidence_bundle": dict(self.evidence_bundle),
            "authority_chain": dict(self.authority_chain),
            "requires_h0st_approval": self.requires_h0st_approval,
        }
        if self.mempalace_comparison is not None:
            payload["mempalace_comparison"] = dict(self.mempalace_comparison)
        return payload


@dataclass(frozen=True, slots=True)
class PromotionAuditReport:
    items: list[PromotionAuditItem]
    contradiction_summary: dict[str, object]
    timestamp: str
    canonical_writes: bool = False
    schema_version: str = PROMOTION_AUDIT_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "canonical_writes": self.canonical_writes,
            "decision_enum": sorted(_DECISIONS),
            "contradiction_summary": dict(self.contradiction_summary),
            "items": [item.to_json_dict() for item in self.items],
        }


def audit_promotion_candidates(
    facts: Sequence[FactCandidate],
    *,
    current_source_hashes: Mapping[str, str] | None = None,
    current_chunk_hashes: Mapping[str, str] | None = None,
    mempalace_comparisons: Sequence[Mapping[str, object]] | None = None,
    timestamp: str,
) -> PromotionAuditReport:
    contradictions = detect_contradictions(facts)
    comparison_by_source = _comparison_by_source(mempalace_comparisons or [])
    items = [
        _audit_fact(
            fact,
            contradictions=contradictions,
            current_source_hashes=current_source_hashes,
            current_chunk_hashes=current_chunk_hashes,
            mempalace_comparison=comparison_by_source.get(fact.source_id),
        )
        for fact in sorted(facts, key=lambda item: (item.subject, item.predicate, item.object, item.source_id, item.chunk_id))
    ]
    return PromotionAuditReport(
        items=items,
        contradiction_summary=_contradiction_summary(contradictions),
        timestamp=timestamp,
        canonical_writes=False,
    )


def write_promotion_audit_json(path: str | Path, report: PromotionAuditReport) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _audit_fact(
    fact: FactCandidate,
    *,
    contradictions: Sequence[Contradiction],
    current_source_hashes: Mapping[str, str] | None,
    current_chunk_hashes: Mapping[str, str] | None,
    mempalace_comparison: Mapping[str, object] | None,
) -> PromotionAuditItem:
    reasons: list[str] = []
    if fact.authority is not AuthorityClass.USER_DIRECT:
        reasons.append("not_user_direct_authority")
    if fact.evidence_authority is not AuthorityClass.USER_DIRECT:
        reasons.append("not_user_direct_evidence")
    if fact.authority is AuthorityClass.DERIVED_SUMMARY or fact.predicate == "co_occurs_with":
        reasons.append("derived_fact_not_promotable")
    if fact.claims_user_approval and fact.authority is not AuthorityClass.USER_DIRECT:
        reasons.append("approval_promotion")
    reasons.extend(_freshness_reasons(fact, current_source_hashes, current_chunk_hashes))
    if _has_contradiction(fact, contradictions):
        reasons.append("contradiction_present")
    safe_comparison = _sanitize_mempalace_comparison(mempalace_comparison)
    if safe_comparison and safe_comparison.get("category") == "agree":
        reasons.append("mempalace_agreement_non_authoritative")
    if safe_comparison and safe_comparison.get("category") == "diverge" and not reasons:
        reasons.append("mempalace_divergence_requires_review")
    reasons = sorted(set(reasons))
    decision = _decision_for_reasons(reasons)
    return PromotionAuditItem(
        subject=_safe_report_value(fact.subject),
        predicate=_safe_report_value(fact.predicate),
        object=_safe_report_value(fact.object),
        decision=decision,
        reasons=reasons,
        evidence_bundle=_evidence_bundle(fact),
        authority_chain={
            "candidate_authority": fact.authority.value,
            "evidence_authority": fact.evidence_authority.value,
        },
        requires_h0st_approval=True,
        mempalace_comparison=safe_comparison,
    )


def _decision_for_reasons(reasons: Sequence[str]) -> str:
    if not reasons:
        return "promotable_candidate"
    if reasons == ["mempalace_divergence_requires_review"]:
        return "needs_h0st_approval"
    return "blocked"


def _freshness_reasons(
    fact: FactCandidate,
    current_source_hashes: Mapping[str, str] | None,
    current_chunk_hashes: Mapping[str, str] | None,
) -> list[str]:
    reasons: list[str] = []
    if current_source_hashes is None or fact.source_id not in current_source_hashes:
        reasons.append("missing_source_hash_verification")
    elif current_source_hashes[fact.source_id] != fact.source_content_hash:
        reasons.append("stale_source_hash")
    if current_chunk_hashes is None or fact.chunk_id not in current_chunk_hashes:
        reasons.append("missing_chunk_hash_verification")
    elif current_chunk_hashes[fact.chunk_id] != fact.content_hash:
        reasons.append("stale_chunk_hash")
    return reasons


def _has_contradiction(fact: FactCandidate, contradictions: Sequence[Contradiction]) -> bool:
    subject = _norm(fact.subject)
    predicate = _norm(fact.predicate)
    return any(item.subject == subject and item.predicate == predicate for item in contradictions)


def _contradiction_summary(contradictions: Sequence[Contradiction]) -> dict[str, object]:
    return {
        "coverage": "local_candidates_only_non_exhaustive",
        "count": len(contradictions),
        "items": [
            {
                "subject": _safe_report_value(item.subject),
                "predicate": _safe_report_value(item.predicate),
                "objects": [_safe_report_value(value) for value in item.objects],
                "fact_ids": [_safe_report_value(value) for value in item.fact_ids],
            }
            for item in contradictions
        ],
    }


def _evidence_bundle(fact: FactCandidate) -> dict[str, object]:
    return {
        "source_id": _safe_report_value(fact.source_id),
        "source_uri": _safe_report_value(fact.source_uri),
        "chunk_id": _safe_report_value(fact.chunk_id),
        "content_hash": _safe_report_value(fact.content_hash),
        "source_content_hash": _safe_report_value(fact.source_content_hash),
        "span": {"start": fact.span_start, "end": fact.span_end},
        "authority": fact.evidence_authority.value,
    }


def _comparison_by_source(comparisons: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    by_source: dict[str, Mapping[str, object]] = {}
    for comparison in comparisons:
        for source in comparison.get("mempalace_sources", []) or []:
            if isinstance(source, str):
                by_source[source] = comparison
    return by_source


def _sanitize_mempalace_comparison(comparison: Mapping[str, object] | None) -> dict[str, object] | None:
    if comparison is None:
        return None
    return {
        "category": _safe_report_value(str(comparison.get("category", ""))),
        "mempalace_drawers": [_safe_report_value(str(item)) for item in comparison.get("mempalace_drawers", []) or []],
        "mempalace_sources": [_safe_report_value(str(item)) for item in comparison.get("mempalace_sources", []) or []],
        "notes_count": len(comparison.get("notes", []) or []),
        "authority": AuthorityClass.DERIVED_SUMMARY.value,
    }


def _reject_canonical_vault_output(path: Path) -> None:
    resolved_vault = Path("/opt/obs/vault").resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_vault or resolved_vault in resolved_path.parents:
        raise ValueError("promotion audit output must not be inside canonical vault")


def _safe_report_value(value: str) -> str:
    if _SECRET_TERM_RE.search(value):
        return "[REDACTED_SECRET_TERM]"
    if _ABSOLUTE_PATH_RE.search(value):
        return _ABSOLUTE_PATH_RE.sub("[REDACTED_PATH]", value)
    return value


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())
