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
