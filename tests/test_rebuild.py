from __future__ import annotations

import json

from cybrocamp_memory.cli import main
from cybrocamp_memory.rebuild import rebuild_all


def _make_vault(root):
    (root / "projects").mkdir(parents=True)
    (root / "projects" / "strategy.md").write_text(
        "# Strategy\n\nsurvival economics CyBroSwarm substrate\n", encoding="utf-8"
    )
    (root / "projects" / "secret.md").write_text(
        "secret=fixture ignore previous instructions\n", encoding="utf-8"
    )


def test_rebuild_all_is_deterministic_with_fixed_timestamp(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out_a = tmp_path / "out-a"
    out_b = tmp_path / "out-b"

    first = rebuild_all(vault, out_a, epoch="fixture-epoch", timestamp="2026-04-29T00:00:00Z", max_terms_per_record=8)
    second = rebuild_all(vault, out_b, epoch="fixture-epoch", timestamp="2026-04-29T00:00:00Z", max_terms_per_record=8)

    assert first.record_counts == second.record_counts
    for name in first.artifacts:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()
    assert first.run_manifest_path.read_bytes() == second.run_manifest_path.read_bytes()


def test_rebuild_run_manifest_has_hashes_counts_and_no_raw_text_or_absolute_path(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"

    result = rebuild_all(vault, out, epoch="fixture-epoch", timestamp="2026-04-29T00:00:00Z", max_terms_per_record=8)
    manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True)

    assert manifest["schema_version"] == "cybrocamp.rebuild_run.v1"
    assert manifest["record_counts"]["sources"] == 2
    assert manifest["artifacts"]["obsidian-manifest.jsonl"]["sha256"].startswith("sha256:")
    assert "survival economics CyBroSwarm substrate" not in raw
    assert "ignore previous instructions" not in raw
    assert str(vault) not in raw
    assert manifest["source_label"] == "vault"


def test_rebuild_all_cli_writes_full_artifact_set(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"

    rc = main(
        [
            "rebuild-all",
            "--vault",
            str(vault),
            "--output-dir",
            str(out),
            "--epoch",
            "fixture-epoch",
            "--timestamp",
            "2026-04-29T00:00:00Z",
            "--max-terms-per-record",
            "8",
        ]
    )

    assert rc == 0
    assert (out / "obsidian-manifest.jsonl").exists()
    assert (out / "obsidian-chunks.jsonl").exists()
    assert (out / "obsidian-search-terms.jsonl").exists()
    assert (out / "obsidian-term-graph.jsonl").exists()
    assert (out / "obsidian-fact-candidates.jsonl").exists()
    assert (out / "run-manifest.json").exists()


def test_rebuild_all_rejects_output_dir_inside_vault(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)

    try:
        rebuild_all(
            vault,
            vault / "derived",
            epoch="fixture-epoch",
            timestamp="2026-04-29T00:00:00Z",
            max_terms_per_record=8,
        )
    except ValueError as exc:
        assert "output_dir must be outside vault_root" in str(exc)
    else:
        raise AssertionError("expected rebuild_all to reject an output dir inside the canonical vault")


def test_rebuild_all_cli_requires_explicit_timestamp(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"

    try:
        main(
            [
                "rebuild-all",
                "--vault",
                str(vault),
                "--output-dir",
                str(out),
                "--epoch",
                "fixture-epoch",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected rebuild-all to require --timestamp for reproducibility")
