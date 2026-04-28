from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cybrocamp_memory.manifest import (
    SourceRecord,
    compute_content_hash,
    manifest_records_from_obsidian,
    write_manifest_jsonl,
)
from cybrocamp_memory.schema import AuthorityClass


def test_content_hash_is_algorithm_prefixed_and_changes_with_content():
    assert compute_content_hash("alpha") == compute_content_hash(b"alpha")
    assert compute_content_hash("alpha").startswith("sha256:")
    assert compute_content_hash("alpha") != compute_content_hash("beta")


def test_obsidian_source_id_is_stable_across_absolute_vault_roots(tmp_path):
    vault_a = tmp_path / "a" / "vault"
    vault_b = tmp_path / "b" / "vault"
    note_rel = Path("projects/cybrocamp/note.md")
    (vault_a / note_rel.parent).mkdir(parents=True)
    (vault_b / note_rel.parent).mkdir(parents=True)
    (vault_a / note_rel).write_text("same text", encoding="utf-8")
    (vault_b / note_rel).write_text("same text", encoding="utf-8")

    record_a = SourceRecord.from_obsidian_note(vault_a, vault_a / note_rel)
    record_b = SourceRecord.from_obsidian_note(vault_b, vault_b / note_rel)

    assert record_a.source_id == record_b.source_id
    assert record_a.uri == "obsidian://projects/cybrocamp/note.md"
    assert record_a.content_hash == record_b.content_hash


def test_content_edit_changes_hash_not_source_id(tmp_path):
    vault = tmp_path / "vault"
    note = vault / "projects" / "cybrocamp" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("first", encoding="utf-8")
    first = SourceRecord.from_obsidian_note(vault, note)

    note.write_text("second", encoding="utf-8")
    second = SourceRecord.from_obsidian_note(vault, note)

    assert first.source_id == second.source_id
    assert first.content_hash != second.content_hash


def test_obsidian_adapter_rejects_symlink_escape(tmp_path):
    vault = tmp_path / "vault"
    outside = tmp_path / "outside.md"
    vault.mkdir()
    outside.write_text("secret outside vault", encoding="utf-8")
    os.symlink(outside, vault / "leak.md")

    with pytest.raises(ValueError, match="outside vault"):
        SourceRecord.from_obsidian_note(vault, vault / "leak.md")


def test_manifest_scan_only_returns_markdown_records_and_ignores_dot_obsidian(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "projects").mkdir()
    (vault / "projects" / "note.md").write_text("visible", encoding="utf-8")
    (vault / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
    (vault / "binary.bin").write_bytes(b"raw")

    records = list(manifest_records_from_obsidian(vault))

    assert [record.uri for record in records] == ["obsidian://projects/note.md"]
    assert records[0].authority is AuthorityClass.CANONICAL_VAULT


def test_manifest_writer_is_idempotent_and_jsonl(tmp_path):
    vault = tmp_path / "vault"
    note = vault / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("hello", encoding="utf-8")
    record = SourceRecord.from_obsidian_note(vault, note)
    manifest_path = tmp_path / "data" / "manifest.jsonl"

    write_manifest_jsonl(manifest_path, [record, record])
    first_bytes = manifest_path.read_bytes()
    write_manifest_jsonl(manifest_path, [record])
    second_bytes = manifest_path.read_bytes()

    assert first_bytes == second_bytes
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    decoded = json.loads(lines[0])
    assert decoded["source_id"] == record.source_id
    assert decoded["authority"] == "canonical_vault"
