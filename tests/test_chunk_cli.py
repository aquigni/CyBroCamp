from __future__ import annotations

import json

from cybrocamp_memory.cli import main


def test_chunk_cli_writes_obsidian_chunk_manifest(tmp_path):
    vault = tmp_path / "vault"
    output = tmp_path / "sidecar" / "chunks.jsonl"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / "note.md").write_text("# Title\n\nhello", encoding="utf-8")

    exit_code = main(["chunks", "obsidian", "--vault", str(vault), "--output", str(output), "--max-chars", "100"])

    assert exit_code == 0
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["source_uri"] == "obsidian://projects/note.md"
    assert decoded["schema_version"] == "cybrocamp.chunk_record.v1"
