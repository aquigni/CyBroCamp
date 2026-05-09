from __future__ import annotations

import json

from cybrocamp_memory.cli import main


def test_manifest_cli_writes_obsidian_manifest(tmp_path):
    vault = tmp_path / "vault"
    output = tmp_path / "sidecar" / "manifest.jsonl"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / "note.md").write_text("hello", encoding="utf-8")

    exit_code = main(["manifest", "obsidian", "--vault", str(vault), "--output", str(output)])

    assert exit_code == 0
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["uri"] == "obsidian://projects/note.md"


def test_cortex_pulse_cli_writes_lightweight_associative_daemon_artifact(tmp_path):
    output = tmp_path / "cortex-pulse.json"
    state = tmp_path / "previous-state.json"
    state.write_text(json.dumps({"vault_epoch": "old"}), encoding="utf-8")
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"events": [{"event_id": "evt1", "summary": "Mac0sh timeout", "source_ref": "a2a:1"}]}), encoding="utf-8")
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"auto_promotion": {"available": True, "latest_entry": {"quarantined_or_rejected": "50"}}}), encoding="utf-8")

    exit_code = main(
        [
            "cortex-pulse",
            "--timestamp",
            "2026-05-10T00:00:00Z",
            "--vault-epoch",
            "new",
            "--previous-state",
            str(state),
            "--event-ledger",
            str(ledger),
            "--dream-context",
            str(context),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == "cybrocamp.incremental_cortex_pulse.v1"
    assert data["should_rebuild"] is True
    assert data["metrics"]["probe_count"] >= 20
    assert data["output_policy"]["canonical_writes"] is False
