from __future__ import annotations

import json
from pathlib import Path

from cybrocamp_memory.cli import main
from cybrocamp_memory.fact_cache import FactCandidate
from cybrocamp_memory.promotion_audit import audit_promotion_candidates
from cybrocamp_memory.schema import AuthorityClass


def _fact(
    *,
    subject="alpha",
    predicate="approved_relation",
    object="omega",
    source_id="source-1",
    source_uri=None,
    chunk_id="chunk-1",
    authority=AuthorityClass.USER_DIRECT,
    evidence_authority=AuthorityClass.USER_DIRECT,
    claims_user_approval=False,
):
    return FactCandidate(
        subject=subject,
        predicate=predicate,
        object=object,
        source_id=source_id,
        source_uri=source_uri or f"fixture://{source_id}",
        chunk_id=chunk_id,
        content_hash=f"sha256:{chunk_id}",
        source_content_hash=f"sha256:{source_id}",
        span_start=0,
        span_end=12,
        authority=authority,
        evidence_authority=evidence_authority,
        claims_user_approval=claims_user_approval,
    )


def _source_hashes(*facts):
    return {fact.source_id: fact.source_content_hash for fact in facts}


def _chunk_hashes(*facts):
    return {fact.chunk_id: fact.content_hash for fact in facts}


def test_user_direct_fresh_noncontradictory_fact_is_promotable_candidate():
    fact = _fact()

    report = audit_promotion_candidates(
        [fact],
        current_source_hashes=_source_hashes(fact),
        current_chunk_hashes=_chunk_hashes(fact),
        timestamp="2026-04-29T00:00:00Z",
    )

    assert report.canonical_writes is False
    assert report.items[0].decision == "promotable_candidate"
    assert report.items[0].requires_h0st_approval is True
    assert report.items[0].evidence_bundle["content_hash"] == fact.content_hash
    assert "raw_text" not in report.to_json_dict()["items"][0]


def test_missing_freshness_verification_blocks_even_user_direct_fact():
    fact = _fact()

    report = audit_promotion_candidates([fact], timestamp="2026-04-29T00:00:00Z")

    assert report.items[0].decision == "blocked"
    assert "missing_source_hash_verification" in report.items[0].reasons
    assert "missing_chunk_hash_verification" in report.items[0].reasons


def test_derived_fact_is_blocked_even_when_mempalace_agrees():
    fact = _fact(
        predicate="co_occurs_with",
        authority=AuthorityClass.DERIVED_SUMMARY,
        evidence_authority=AuthorityClass.CANONICAL_VAULT,
    )

    report = audit_promotion_candidates(
        [fact],
        current_source_hashes=_source_hashes(fact),
        current_chunk_hashes=_chunk_hashes(fact),
        mempalace_comparisons=[{"category": "agree", "mempalace_drawers": ["drawer_1"], "mempalace_sources": [fact.source_id]}],
        timestamp="2026-04-29T00:00:00Z",
    )

    item = report.items[0]
    assert item.decision == "blocked"
    assert "derived_fact_not_promotable" in item.reasons
    assert "mempalace_agreement_non_authoritative" in item.reasons
    assert item.mempalace_comparison["category"] == "agree"


def test_contradiction_blocks_candidate_and_is_reported_non_exhaustively():
    left = _fact(object="omega", chunk_id="/opt/obs/vault/secret_api_key")
    right = _fact(object="sigma", chunk_id="/tmp/other")

    report = audit_promotion_candidates(
        [left, right],
        current_source_hashes=_source_hashes(left, right),
        current_chunk_hashes=_chunk_hashes(left, right),
        timestamp="2026-04-29T00:00:00Z",
    )

    assert report.contradiction_summary["coverage"] == "local_candidates_only_non_exhaustive"
    assert report.items[0].decision == "blocked"
    assert "contradiction_present" in report.items[0].reasons
    assert report.items[1].decision == "blocked"
    raw = json.dumps(report.to_json_dict(), ensure_ascii=False)
    assert "/opt/obs/vault" not in raw
    assert "secret_api_key" not in raw
    assert "/tmp/other" not in raw


def test_approval_claim_without_user_direct_authority_is_blocked():
    fact = _fact(
        authority=AuthorityClass.CANONICAL_VAULT,
        evidence_authority=AuthorityClass.CANONICAL_VAULT,
        claims_user_approval=True,
    )

    report = audit_promotion_candidates(
        [fact],
        current_source_hashes=_source_hashes(fact),
        current_chunk_hashes=_chunk_hashes(fact),
        timestamp="2026-04-29T00:00:00Z",
    )

    assert report.items[0].decision == "blocked"
    assert "approval_promotion" in report.items[0].reasons


def test_sensitive_or_absolute_path_terms_are_redacted_from_report():
    fact = _fact(
        subject="/opt/obs/vault",
        object="hermes_api_key",
        source_id="/tmp/secret_source",
        source_uri="file:///opt/obs/vault/secret_api_key.md",
        chunk_id="/tmp/chunk",
    )

    report = audit_promotion_candidates(
        [fact],
        current_source_hashes=_source_hashes(fact),
        current_chunk_hashes=_chunk_hashes(fact),
        mempalace_comparisons=[
            {
                "category": "agree",
                "mempalace_drawers": ["/tmp/drawer_with_token"],
                "mempalace_sources": [fact.source_id],
                "notes": ["raw note mentions secret_api_key at /opt/obs/vault/private.md"],
            }
        ],
        timestamp="2026-04-29T00:00:00Z",
    )

    raw = json.dumps(report.to_json_dict(), ensure_ascii=False)
    assert "/opt/obs/vault" not in raw
    assert "/tmp/" not in raw
    assert "hermes_api_key" not in raw
    assert "secret_api_key" not in raw
    assert "drawer_with_token" not in raw
    assert "raw note" not in raw
    assert "[REDACTED_PATH]" in raw
    assert "[REDACTED_SECRET_TERM]" in raw
    assert report.to_json_dict()["items"][0]["mempalace_comparison"]["notes_count"] == 1


def test_evidence_bundle_contains_mandatory_safe_fields():
    fact = _fact()

    report = audit_promotion_candidates(
        [fact],
        current_source_hashes=_source_hashes(fact),
        current_chunk_hashes=_chunk_hashes(fact),
        timestamp="2026-04-29T00:00:00Z",
    )

    evidence = report.to_json_dict()["items"][0]["evidence_bundle"]
    assert {"source_id", "source_uri", "chunk_id", "content_hash", "source_content_hash", "span", "authority"} <= set(evidence)


def test_stale_hash_mismatch_blocks_candidate():
    fact = _fact()

    report = audit_promotion_candidates(
        [fact],
        current_source_hashes={fact.source_id: "sha256:changed-source"},
        current_chunk_hashes={fact.chunk_id: "sha256:changed-chunk"},
        timestamp="2026-04-29T00:00:00Z",
    )

    assert report.items[0].decision == "blocked"
    assert "stale_source_hash" in report.items[0].reasons
    assert "stale_chunk_hash" in report.items[0].reasons


def test_promotion_audit_cli_rejects_output_inside_canonical_vault(tmp_path):
    fact = _fact()
    facts_path = tmp_path / "facts.jsonl"
    facts_path.write_text(json.dumps(fact.to_json_dict(), sort_keys=True) + "\n", encoding="utf-8")

    try:
        main(
            [
                "promotion-audit",
                "--facts",
                str(facts_path),
                "--output",
                "/opt/obs/vault/cybrocamp-stage14-forbidden.json",
                "--timestamp",
                "2026-04-29T00:00:00Z",
            ]
        )
    except ValueError as exc:
        assert "canonical vault" in str(exc)
    else:
        raise AssertionError("expected canonical vault output rejection")


def test_promotion_audit_cli_writes_sanitized_report(tmp_path):
    fact = _fact()
    facts_path = tmp_path / "facts.jsonl"
    facts_path.write_text(json.dumps(fact.to_json_dict(), sort_keys=True) + "\n", encoding="utf-8")
    source_hashes = tmp_path / "source-hashes.json"
    chunk_hashes = tmp_path / "chunk-hashes.json"
    output = tmp_path / "audit.json"
    source_hashes.write_text(json.dumps(_source_hashes(fact), sort_keys=True), encoding="utf-8")
    chunk_hashes.write_text(json.dumps(_chunk_hashes(fact), sort_keys=True), encoding="utf-8")

    rc = main(
        [
            "promotion-audit",
            "--facts",
            str(facts_path),
            "--current-source-hashes",
            str(source_hashes),
            "--current-chunk-hashes",
            str(chunk_hashes),
            "--output",
            str(output),
            "--timestamp",
            "2026-04-29T00:00:00Z",
        ]
    )

    raw = output.read_text(encoding="utf-8")
    report = json.loads(raw)
    assert rc == 0
    assert report["schema_version"] == "cybrocamp.promotion_audit.v1"
    assert report["canonical_writes"] is False
    assert report["items"][0]["decision"] == "promotable_candidate"
    assert "raw" not in raw.lower()
    assert "secret" not in raw.lower()
