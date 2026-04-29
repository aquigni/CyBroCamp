from __future__ import annotations

import json

from cybrocamp_memory.cli import main
from cybrocamp_memory.sister_rollout import build_cortex_rollout, write_cortex_rollout_json


def test_rollout_builds_three_sister_rights_matrix_with_default_deny_future_sisters():
    rollout = build_cortex_rollout(timestamp="2026-04-29T00:00:00Z")
    data = rollout.to_json_dict()

    assert data["schema_version"] == "cybrocamp.cortex_rollout.v1"
    assert data["output_policy"]["canonical_writes"] is False
    assert data["output_policy"]["network_calls"] is False
    node_names = {node["sister_id"] for node in data["sisters"]}
    assert {"chthonya", "mac0sh", "debi0"}.issubset(node_names)
    rights = {node["sister_id"]: node["rights"] for node in data["sisters"]}
    assert rights["chthonya"]["can_build_canonical_index"] is True
    assert rights["mac0sh"]["can_review"] is True
    assert rights["debi0"]["can_execute_promotions"] is False
    assert data["future_sister_template"]["rights"]["can_query"] is True
    assert data["future_sister_template"]["rights"]["can_execute_promotions"] is False
    assert data["future_sister_template"]["status"] == "quarantined_readonly_until_explicit_approval"


def test_rollout_never_grants_future_sister_or_peer_user_approval():
    data = build_cortex_rollout(timestamp="2026-04-29T00:00:00Z").to_json_dict()

    assert data["authority_policy"]["peer_claim_is_user_approval"] is False
    assert data["authority_policy"]["future_auto_enrollment_grants_approval"] is False
    for node in data["sisters"]:
        assert node["rights"]["can_grant_h0st_approval"] is False


def test_rollout_sanitizes_paths_and_tokens(tmp_path):
    rollout = build_cortex_rollout(
        sisters=[
            {"sister_id": "chthonya", "host_label": "/opt/obs/vault token=SUPERSECRET123", "role": "canonical_builder"},
            {"sister_id": "mac0sh", "host_label": "/Users/au/private", "role": "reviewer"},
            {"sister_id": "debi0", "host_label": "debian bounded worker", "role": "bounded_readonly"},
        ],
        timestamp="2026-04-29T00:00:00Z",
    )
    out = tmp_path / "rollout.json"

    write_cortex_rollout_json(out, rollout)
    raw = out.read_text(encoding="utf-8")

    assert "SUPERSECRET123" not in raw
    assert "token=" not in raw
    assert "/opt/obs/vault" not in raw
    assert "/Users/au" not in raw
    assert "[REDACTED" in raw


def test_rollout_cli_writes_config_and_rejects_vault_output(tmp_path):
    output = tmp_path / "rollout.json"
    rc = main(["cortex-rollout", "--output", str(output), "--timestamp", "2026-04-29T00:00:00Z"])
    data = json.loads(output.read_text(encoding="utf-8"))

    assert rc == 0
    assert data["schema_version"] == "cybrocamp.cortex_rollout.v1"
    try:
        main(["cortex-rollout", "--output", "/opt/obs/vault/stage18-rollout.json", "--timestamp", "2026-04-29T00:00:00Z"])
    except ValueError as exc:
        assert "canonical vault" in str(exc)
    else:
        raise AssertionError("expected canonical vault output rejection")
