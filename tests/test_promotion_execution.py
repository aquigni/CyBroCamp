from __future__ import annotations

import json
from pathlib import Path

from cybrocamp_memory.cli import main
from cybrocamp_memory.promotion_execution import build_execution_receipt, write_execution_receipt_json
from cybrocamp_memory.promotion_preview import build_locked_preview


def _preview():
    plan = {
        "schema_version": "cybrocamp.promotion_plan.v1",
        "generated_at": "2026-04-29T00:00:00Z",
        "mode": "dry_run",
        "output_policy": {"canonical_writes": False, "network_calls": False},
        "candidates": [{"candidate_id": "cand-alpha", "status": "approved_for_dry_run"}],
        "dry_run_ops": [
            {
                "op_id": "op-alpha",
                "candidate_id": "cand-alpha",
                "op_type": "promote_to_mempalace_kg",
                "target_kind": "mempalace_kg_candidate",
                "target_id_or_hash": "source-1",
                "sanitized_target_label": "alpha approved_relation omega",
                "dry_run": True,
                "would_write": False,
            }
        ],
    }
    plan_hash = build_locked_preview(plan, timestamp="2026-04-29T00:00:00Z").to_json_dict()["input_plan_hash"]
    lock = {
        "schema_version": "cybrocamp.preview_lock.v1",
        "approved_by": "H0st",
        "plan_hash": plan_hash,
        "locked_ops": [{"op_id": "op-alpha", "action": "preview_canonical_write", "approved_by": "H0st"}],
    }
    return build_locked_preview(plan, lock_scope=lock, timestamp="2026-04-29T00:00:00Z").to_json_dict()


def _execution_scope(preview_hash: str):
    return {
        "schema_version": "cybrocamp.execution_approval.v1",
        "approved_by": "H0st",
        "preview_hash": preview_hash,
        "approved_ops": [{"op_id": "op-alpha", "action": "execute_mempalace_kg_promotion", "approved_by": "H0st"}],
    }


def test_execution_without_explicit_second_approval_executes_nothing():
    receipt = build_execution_receipt(_preview(), timestamp="2026-04-29T00:00:00Z")
    data = receipt.to_json_dict()

    assert data["schema_version"] == "cybrocamp.execution_receipt.v1"
    assert data["mode"] == "controlled_execution"
    assert data["output_policy"]["network_calls"] is False
    assert data["output_policy"]["requires_second_h0st_approval"] is True
    assert data["executed_ops"] == []
    assert data["diagnostics"]["executed_count"] == 0


def test_matching_execution_approval_records_receipt_but_uses_local_sink_only():
    preview = _preview()
    preview_hash = build_execution_receipt(preview, timestamp="2026-04-29T00:00:00Z").to_json_dict()["input_preview_hash"]

    receipt = build_execution_receipt(preview, execution_approval=_execution_scope(preview_hash), timestamp="2026-04-29T00:00:00Z")
    data = receipt.to_json_dict()

    assert data["diagnostics"]["executed_count"] == 1
    op = data["executed_ops"][0]
    assert op["op_id"] == "op-alpha"
    assert op["sink"] == "local_receipt_only"
    assert op["canonical_network_write_performed"] is False
    assert op["receipt_hash"].startswith("sha256:")


def test_execution_approval_is_bound_to_preview_hash_and_exact_action():
    receipt = build_execution_receipt(
        _preview(),
        execution_approval={
            "schema_version": "cybrocamp.execution_approval.v1",
            "approved_by": "H0st",
            "preview_hash": "sha256:wrong",
            "approved_ops": [{"op_id": "op-alpha", "action": "execute_other", "approved_by": "H0st"}],
        },
        timestamp="2026-04-29T00:00:00Z",
    ).to_json_dict()

    assert receipt["executed_ops"] == []
    assert "missing_or_mismatched_execution_approval" in receipt["reviewed_ops"][0]["block_reasons"]


def test_execution_receipt_is_deterministic_sanitized_and_vault_guarded(tmp_path):
    preview = _preview()
    preview["preview_writes"][0]["op_id"] = "op-token=SUPERSECRET123"
    preview["preview_writes"][0]["target_id_or_hash"] = "/opt/obs/vault/private.md"
    first = build_execution_receipt(preview, timestamp="2026-04-29T00:00:00Z")
    second = build_execution_receipt(preview, timestamp="2026-04-29T00:00:00Z")
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    write_execution_receipt_json(first_path, first)
    write_execution_receipt_json(second_path, second)
    raw = first_path.read_text(encoding="utf-8")

    assert first_path.read_bytes() == second_path.read_bytes()
    assert "SUPERSECRET123" not in raw
    assert "token=" not in raw
    assert "/opt/obs/vault" not in raw
    try:
        write_execution_receipt_json("/opt/obs/vault/stage17-receipt.json", first)
    except ValueError as exc:
        assert "canonical vault" in str(exc)
    else:
        raise AssertionError("expected canonical vault output rejection")


def test_promotion_execute_cli_writes_local_receipt(tmp_path):
    preview_path = tmp_path / "preview.json"
    output_path = tmp_path / "receipt.json"
    preview_path.write_text(json.dumps(_preview(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "promotion-execute",
            "--preview",
            str(preview_path),
            "--output",
            str(output_path),
            "--timestamp",
            "2026-04-29T00:00:00Z",
        ]
    )

    assert exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "cybrocamp.execution_receipt.v1"
    assert data["executed_ops"] == []
    assert data["output_policy"]["canonical_writes"] is False
