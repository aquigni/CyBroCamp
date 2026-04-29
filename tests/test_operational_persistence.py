from __future__ import annotations

import json

from cybrocamp_memory.cli import main
from cybrocamp_memory.operational_persistence import (
    build_persistence_bundle,
    write_persistence_bundle,
)


def test_persistence_bundle_is_safe_user_systemd_plan(tmp_path):
    bundle = build_persistence_bundle(
        repo_root="/home/chthonya/projects/cybrocamp-memory",
        vault_root="/opt/obs/vault",
        artifact_root="/home/chthonya/.local/share/cybrocamp/cortex",
        interval_minutes=30,
    )

    assert bundle["schema_version"] == "cybrocamp.operational_persistence.v1"
    assert bundle["safety_envelope"] == {
        "canonical_writes": False,
        "network_calls": False,
        "approval_state_writes": False,
        "writes_inside_vault": False,
        "user_systemd_only": True,
    }
    assert bundle["paths"]["vault_root"] == "/opt/obs/vault"
    assert bundle["paths"]["artifact_root"] == "/home/chthonya/.local/share/cybrocamp/cortex"
    assert "Persistent=true" in bundle["systemd_timer"]
    assert "OnUnitActiveSec=30min" in bundle["systemd_timer"]
    assert "rebuild-all" in bundle["runner_script"]
    assert "--output-dir" in bundle["runner_script"]
    assert "/opt/obs/vault" in bundle["runner_script"]
    assert ".local/share/cybrocamp/cortex/current" in bundle["runner_script"]
    assert "systemctl restart" not in json.dumps(bundle, ensure_ascii=False)
    assert "sudo" not in json.dumps(bundle, ensure_ascii=False)


def test_persistence_bundle_rejects_artifact_root_inside_vault(tmp_path):
    try:
        build_persistence_bundle(
            repo_root=tmp_path / "repo",
            vault_root=tmp_path / "vault",
            artifact_root=tmp_path / "vault" / "derived",
        )
    except ValueError as exc:
        assert "artifact_root must be outside vault_root" in str(exc)
    else:
        raise AssertionError("expected artifact_root inside vault to be rejected")


def test_persistence_bundle_rejects_canonical_vault_even_with_different_vault_root(tmp_path):
    try:
        build_persistence_bundle(
            repo_root=tmp_path / "repo",
            vault_root=tmp_path / "vault",
            artifact_root="/opt/obs/vault/derived",
        )
    except ValueError as exc:
        assert "/opt/obs/vault" in str(exc)
    else:
        raise AssertionError("expected canonical vault artifact root to be rejected")


def test_persistence_runner_promotes_smoke_recall_atomically(tmp_path):
    bundle = build_persistence_bundle(
        repo_root=tmp_path / "repo",
        vault_root=tmp_path / "vault",
        artifact_root=tmp_path / "artifacts",
    )
    runner = bundle["runner_script"]
    assert '--output "$OUTPUT_DIR/.last-smoke-recall.json.tmp"' in runner
    assert 'mv "$OUTPUT_DIR/.last-smoke-recall.json.tmp" "$OUTPUT_DIR/last-smoke-recall.json"' in runner


def test_write_persistence_bundle_creates_files_atomically(tmp_path):
    bundle = build_persistence_bundle(
        repo_root=tmp_path / "repo",
        vault_root=tmp_path / "vault",
        artifact_root=tmp_path / "artifacts",
        interval_minutes=45,
    )
    out = tmp_path / "bundle"

    written = write_persistence_bundle(out, bundle)

    assert (out / "cybrocamp-cortex-rebuild.sh").exists()
    assert (out / "cybrocamp-cortex-rebuild.service").exists()
    assert (out / "cybrocamp-cortex-rebuild.timer").exists()
    assert (out / "persistence-bundle.json").exists()
    assert (out / "cybrocamp-cortex-rebuild.sh").stat().st_mode & 0o111
    assert written["runner_script"].name == "cybrocamp-cortex-rebuild.sh"
    assert "OnUnitActiveSec=45min" in (out / "cybrocamp-cortex-rebuild.timer").read_text(encoding="utf-8")


def test_persistence_bundle_cli_writes_installable_bundle(tmp_path):
    out = tmp_path / "bundle"

    rc = main(
        [
            "persistence-bundle",
            "--repo-root",
            str(tmp_path / "repo"),
            "--vault",
            str(tmp_path / "vault"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--output-dir",
            str(out),
            "--interval-minutes",
            "20",
        ]
    )

    assert rc == 0
    manifest = json.loads((out / "persistence-bundle.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "cybrocamp.operational_persistence.v1"
    assert "OnUnitActiveSec=20min" in (out / "cybrocamp-cortex-rebuild.timer").read_text(encoding="utf-8")
