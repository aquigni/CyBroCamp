from __future__ import annotations

from cybrocamp_memory.consolidation import decide_promotion, detect_contradictions
from cybrocamp_memory.fact_cache import FactCandidate
from cybrocamp_memory.schema import AuthorityClass


def _fact(subject: str, predicate: str, obj: str, *, authority=AuthorityClass.CANONICAL_VAULT, evidence_authority=None) -> FactCandidate:
    return FactCandidate(
        subject=subject,
        predicate=predicate,
        object=obj,
        source_id="source",
        source_uri="obsidian://source.md",
        chunk_id=f"chunk-{subject}-{obj}",
        content_hash="sha256:chunk",
        source_content_hash="sha256:source",
        span_start=0,
        span_end=10,
        authority=authority,
        evidence_authority=evidence_authority or authority,
    )


def test_detect_contradictions_for_same_subject_predicate_different_objects():
    facts = [_fact("service", "status", "active"), _fact("service", "status", "dead")]

    contradictions = detect_contradictions(facts)

    assert contradictions
    assert contradictions[0].subject == "service"
    assert contradictions[0].predicate == "status"
    assert contradictions[0].objects == ["active", "dead"]


def test_derived_fact_is_not_promotable_without_user_direct_authority():
    fact = _fact("cybrocamp", "co_occurs_with", "approval", authority=AuthorityClass.DERIVED_SUMMARY)

    decision = decide_promotion(fact, [])

    assert decision.can_promote is False
    assert "not_user_direct_authority" in decision.reasons


def test_user_direct_fact_can_be_promoted_when_fresh_and_uncontradicted():
    fact = _fact("preference", "approved", "yes", authority=AuthorityClass.USER_DIRECT)

    decision = decide_promotion(fact, [], current_source_hashes={"source": "sha256:source"}, current_chunk_hashes={fact.chunk_id: "sha256:chunk"})

    assert decision.can_promote is True
    assert decision.reasons == []


def test_stale_or_contradicted_fact_is_not_promotable():
    fact = _fact("preference", "approved", "yes", authority=AuthorityClass.USER_DIRECT)
    contradiction = detect_contradictions([fact, _fact("preference", "approved", "no", authority=AuthorityClass.USER_DIRECT)])

    stale = decide_promotion(fact, [], current_source_hashes={"source": "sha256:new"})
    blocked = decide_promotion(fact, contradiction, current_source_hashes={"source": "sha256:source"})

    assert stale.can_promote is False
    assert "stale_source_hash" in stale.reasons
    assert blocked.can_promote is False
    assert "contradiction_present" in blocked.reasons
