from __future__ import annotations

import json
from pathlib import Path

from cybrocamp_memory.cli import main
from cybrocamp_memory.fact_cache import FactCandidate
from cybrocamp_memory.promotion_audit import audit_promotion_candidates
from cybrocamp_memory.promotion_plan import build_promotion_plan, write_promotion_plan_json
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
    )


def _audit_dict(*facts):
    source_hashes = {fact.source_id: fact.source_content_hash for fact in facts}
    chunk_hashes = {fact.chunk_id: fact.content_hash for fact in facts}
    return audit_promotion_candidates(
        list(facts),
        current_source_hashes=source_hashes,
        current_chunk_hashes=chunk_hashes,
        timestamp="2026-04-29T00:00:00Z",
    ).to_json_dict()


def _approval(candidate_id: str, *, action="promote_to_mempalace_kg"):
    return {
        "schema_version": "cybrocamp.approval_scope.v1",
        "approved_by": "H0st",
        "approval_scope_id": "scope-stage15-1",
        "approved_candidates": [
            {
                "candidate_id": candidate_id,
                "action": action,
                "approved_by": "H0st",
                "approval_scope_id": "scope-stage15-1",
            }
        ],
    }


def test_no_approval_scope_yields_zero_dry_run_ops():
    audit = _audit_dict(_fact())

    plan = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z")
    data = plan.to_json_dict()

    assert data["schema_version"] == "cybrocamp.promotion_plan.v1"
    assert data["mode"] == "dry_run"
    assert data["output_policy"]["canonical_writes"] is False
    assert data["output_policy"]["network_calls"] is False
    assert data["diagnostics"]["approved_ops_count"] == 0
    assert data["dry_run_ops"] == []
    assert data["candidates"][0]["status"] == "requires_approval"
    assert data["candidates"][0]["approval_required"] is True


def test_matching_h0st_approval_creates_non_writing_dry_run_op():
    audit = _audit_dict(_fact())
    candidate_id = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z").to_json_dict()["candidates"][0]["candidate_id"]

    plan = build_promotion_plan(audit, approval_scope=_approval(candidate_id), timestamp="2026-04-29T00:00:00Z")
    data = plan.to_json_dict()

    assert data["diagnostics"]["approved_ops_count"] == 1
    assert data["candidates"][0]["status"] == "approved_for_dry_run"
    assert data["dry_run_ops"][0]["candidate_id"] == candidate_id
    assert data["dry_run_ops"][0]["dry_run"] is True
    assert data["dry_run_ops"][0]["would_write"] is False
    assert data["dry_run_ops"][0]["op_type"] == "promote_to_mempalace_kg"


def test_approval_scope_does_not_authorize_spoofed_candidate_or_action():
    audit = _audit_dict(_fact())
    candidate_id = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z").to_json_dict()["candidates"][0]["candidate_id"]

    spoofed = _approval(candidate_id + "-suffix", action="promote_to_obsidian")
    plan = build_promotion_plan(audit, approval_scope=spoofed, timestamp="2026-04-29T00:00:00Z")
    data = plan.to_json_dict()

    assert data["dry_run_ops"] == []
    assert data["candidates"][0]["status"] == "requires_approval"
    assert "missing_exact_h0st_approval_scope" in data["candidates"][0]["block_reasons"]


def test_blocked_audit_item_never_becomes_operation_even_with_approval():
    audit = _audit_dict(
        _fact(
            predicate="co_occurs_with",
            authority=AuthorityClass.DERIVED_SUMMARY,
            evidence_authority=AuthorityClass.CANONICAL_VAULT,
        )
    )
    candidate_id = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z").to_json_dict()["candidates"][0]["candidate_id"]

    plan = build_promotion_plan(audit, approval_scope=_approval(candidate_id), timestamp="2026-04-29T00:00:00Z")
    data = plan.to_json_dict()

    assert data["dry_run_ops"] == []
    assert data["candidates"][0]["status"] == "blocked_by_audit"
    assert "audit_decision_not_promotable" in data["candidates"][0]["block_reasons"]


def test_plan_rechecks_non_user_direct_authority_even_if_audit_is_spoofed_promotable():
    audit = _audit_dict(_fact())
    audit["items"][0]["decision"] = "promotable_candidate"
    audit["items"][0]["authority_chain"] = {
        "candidate_authority": "a2a_peer_claim",
        "evidence_authority": "local_mempalace",
    }
    candidate_id = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z").to_json_dict()["candidates"][0]["candidate_id"]

    plan = build_promotion_plan(audit, approval_scope=_approval(candidate_id), timestamp="2026-04-29T00:00:00Z")
    data = plan.to_json_dict()

    assert data["dry_run_ops"] == []
    assert data["candidates"][0]["status"] == "blocked_by_audit"
    assert "non_user_direct_authority_not_promotable" in data["candidates"][0]["block_reasons"]


def test_secret_key_value_shapes_are_fully_redacted():
    audit = _audit_dict(
        _fact(
            subject="api_key=SUPERSECRET123",
            predicate="Bearer VERYSECRET456",
            object="password: ULTRASECRET789",
        )
    )

    plan = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z")
    raw = json.dumps(plan.to_json_dict(), sort_keys=True)

    assert "SUPERSECRET123" not in raw
    assert "VERYSECRET456" not in raw
    assert "ULTRASECRET789" not in raw
    assert "api_key=" not in raw
    assert "Bearer VERY" not in raw
    assert "password:" not in raw
    assert "[REDACTED_SECRET]" in raw


def test_plan_output_is_deterministic_and_sanitized(tmp_path):
    audit = _audit_dict(
        _fact(
            subject="/opt/obs/vault/private.md",
            object="hermes_api_key",
            source_id="/tmp/secret-source",
            source_uri="file:///opt/obs/vault/private.md",
            chunk_id="/tmp/chunk",
        )
    )
    first = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z")
    second = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z")
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    write_promotion_plan_json(first_path, first)
    write_promotion_plan_json(second_path, second)

    assert first_path.read_bytes() == second_path.read_bytes()
    raw = first_path.read_text(encoding="utf-8")
    assert "/opt/obs/vault" not in raw
    assert "/tmp/" not in raw
    assert "hermes_api_key" not in raw
    assert "[REDACTED" in raw


def test_promotion_plan_cli_rejects_output_inside_canonical_vault(tmp_path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(_audit_dict(_fact()), sort_keys=True), encoding="utf-8")

    try:
        main(
            [
                "promotion-plan",
                "--audit",
                str(audit_path),
                "--output",
                "/opt/obs/vault/cybrocamp-stage15-forbidden.json",
                "--timestamp",
                "2026-04-29T00:00:00Z",
            ]
        )
    except ValueError as exc:
        assert "canonical vault" in str(exc)
    else:
        raise AssertionError("expected canonical vault output rejection")


def test_promotion_plan_cli_writes_plan_with_approval_scope(tmp_path):
    audit = _audit_dict(_fact())
    candidate_id = build_promotion_plan(audit, timestamp="2026-04-29T00:00:00Z").to_json_dict()["candidates"][0]["candidate_id"]
    audit_path = tmp_path / "audit.json"
    approval_path = tmp_path / "approval.json"
    output = tmp_path / "plan.json"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    approval_path.write_text(json.dumps(_approval(candidate_id), sort_keys=True), encoding="utf-8")

    rc = main(
        [
            "promotion-plan",
            "--audit",
            str(audit_path),
            "--approval-scope",
            str(approval_path),
            "--output",
            str(output),
            "--timestamp",
            "2026-04-29T00:00:00Z",
        ]
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert rc == 0
    assert data["schema_version"] == "cybrocamp.promotion_plan.v1"
    assert data["diagnostics"]["approved_ops_count"] == 1
    assert data["dry_run_ops"][0]["would_write"] is False
