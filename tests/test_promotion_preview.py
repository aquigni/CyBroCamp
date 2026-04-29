from __future__ import annotations

import json
from pathlib import Path

from cybrocamp_memory.cli import main
from cybrocamp_memory.promotion_preview import build_locked_preview, write_locked_preview_json


def _plan(candidate_id="cand-alpha", *, approved=True):
    return {
        "schema_version": "cybrocamp.promotion_plan.v1",
        "generated_at": "2026-04-29T00:00:00Z",
        "mode": "dry_run",
        "output_policy": {
            "canonical_writes": False,
            "network_calls": False,
        },
        "candidates": [
            {
                "candidate_id": candidate_id,
                "sanitized_title": "alpha approved_relation omega",
                "status": "approved_for_dry_run" if approved else "requires_approval",
                "source_authority": "user_direct",
                "evidence_authority": "user_direct",
            }
        ],
        "dry_run_ops": [
            {
                "op_id": "op-alpha",
                "candidate_id": candidate_id,
                "op_type": "promote_to_mempalace_kg",
                "dry_run": True,
                "would_write": False,
                "target_kind": "mempalace_kg_candidate",
                "target_id_or_hash": "source-1",
                "sanitized_target_label": "alpha approved_relation omega",
                "preconditions": ["dry_run_only_no_canonical_write"],
            }
        ]
        if approved
        else [],
    }


def _lock_scope(plan_hash: str, op_id="op-alpha"):
    return {
        "schema_version": "cybrocamp.preview_lock.v1",
        "approved_by": "H0st",
        "plan_hash": plan_hash,
        "locked_ops": [{"op_id": op_id, "action": "preview_canonical_write", "approved_by": "H0st"}],
    }


def test_locked_preview_without_second_lock_contains_zero_preview_writes():
    preview = build_locked_preview(_plan(), timestamp="2026-04-29T00:00:00Z")
    data = preview.to_json_dict()

    assert data["schema_version"] == "cybrocamp.locked_preview.v1"
    assert data["mode"] == "locked_preview_only"
    assert data["output_policy"]["canonical_writes"] is False
    assert data["output_policy"]["network_calls"] is False
    assert data["preview_writes"] == []
    assert data["diagnostics"]["lock_required"] is True


def test_matching_lock_scope_creates_sanitized_non_writing_preview_and_receipt_draft():
    plan = _plan()
    plan_hash = build_locked_preview(plan, timestamp="2026-04-29T00:00:00Z").to_json_dict()["input_plan_hash"]

    preview = build_locked_preview(plan, lock_scope=_lock_scope(plan_hash), timestamp="2026-04-29T00:00:00Z")
    data = preview.to_json_dict()

    assert data["diagnostics"]["locked_preview_count"] == 1
    item = data["preview_writes"][0]
    assert item["op_id"] == "op-alpha"
    assert item["would_write"] is False
    assert item["canonical_write_enabled"] is False
    assert item["receipt_draft"]["receipt_schema_version"] == "cybrocamp.promotion_receipt.v1"
    assert item["receipt_draft"]["execution_allowed"] is False
    assert item["receipt_draft"]["approval_layer"] == "preview_lock_only"


def test_lock_scope_is_bound_to_exact_plan_hash_and_op():
    plan = _plan()
    preview = build_locked_preview(
        plan,
        lock_scope={
            "schema_version": "cybrocamp.preview_lock.v1",
            "approved_by": "H0st",
            "plan_hash": "sha256:wrong",
            "locked_ops": [{"op_id": "op-alpha", "action": "preview_canonical_write", "approved_by": "H0st"}],
        },
        timestamp="2026-04-29T00:00:00Z",
    ).to_json_dict()

    assert preview["preview_writes"] == []
    assert "missing_or_mismatched_preview_lock" in preview["preview_ops"][0]["block_reasons"]


def test_locked_preview_sanitizes_secret_and_path_surfaces(tmp_path):
    plan = _plan(candidate_id="cand-/opt/obs/vault/private-token")
    plan["dry_run_ops"][0]["op_id"] = "op-api_key=SUPERSECRET123"
    plan["dry_run_ops"][0]["target_id_or_hash"] = "/opt/obs/vault/private.md"
    plan_hash = build_locked_preview(plan, timestamp="2026-04-29T00:00:00Z").to_json_dict()["input_plan_hash"]
    preview = build_locked_preview(plan, lock_scope=_lock_scope(plan_hash, op_id="op-api_key=SUPERSECRET123"), timestamp="2026-04-29T00:00:00Z")
    out = tmp_path / "preview.json"

    write_locked_preview_json(out, preview)
    raw = out.read_text(encoding="utf-8")

    assert "SUPERSECRET123" not in raw
    assert "api_key=" not in raw
    assert "/opt/obs/vault" not in raw
    assert "[REDACTED" in raw


def test_locked_preview_writer_rejects_canonical_vault_output():
    try:
        write_locked_preview_json("/opt/obs/vault/stage16-preview.json", build_locked_preview(_plan(), timestamp="2026-04-29T00:00:00Z"))
    except ValueError as exc:
        assert "canonical vault" in str(exc)
    else:
        raise AssertionError("expected canonical vault output rejection")


def test_promotion_preview_cli_writes_locked_preview(tmp_path):
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "preview.json"
    plan_path.write_text(json.dumps(_plan(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "promotion-preview",
            "--plan",
            str(plan_path),
            "--output",
            str(output_path),
            "--timestamp",
            "2026-04-29T00:00:00Z",
        ]
    )

    assert exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "cybrocamp.locked_preview.v1"
    assert data["preview_writes"] == []
