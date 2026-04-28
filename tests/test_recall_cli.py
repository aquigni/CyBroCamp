from __future__ import annotations

import json

from cybrocamp_memory.chunks import ChunkRecord, write_chunk_manifest_jsonl
from cybrocamp_memory.cli import main
from cybrocamp_memory.manifest import SourceRecord
from cybrocamp_memory.schema import AuthorityClass


def _chunk(text: str) -> ChunkRecord:
    source = SourceRecord(
        source_id="source-1",
        uri="obsidian://demo.md",
        authority=AuthorityClass.CANONICAL_VAULT,
        epoch="fixture",
        content_hash="sha256:source",
        created_at="2026-04-29T00:00:00Z",
    )
    return ChunkRecord.from_text(source, 0, text, 0, len(text.encode("utf-8")))


def test_recall_cli_reads_chunk_manifest_and_writes_recallpacket(tmp_path):
    manifest = tmp_path / "chunks.jsonl"
    output = tmp_path / "recall.json"
    write_chunk_manifest_jsonl(manifest, [_chunk("hippocampus cortex recall")])

    exit_code = main([
        "recall",
        "--chunks",
        str(manifest),
        "--query",
        "hippocampus",
        "--output",
        str(output),
        "--timestamp",
        "2026-04-29T00:00:00Z",
    ])

    assert exit_code == 0
    decoded = json.loads(output.read_text(encoding="utf-8"))
    assert decoded["query"] == "hippocampus"
    assert decoded["items"][0]["evidence"]["chunk_id"]
    assert "hippocampus cortex recall" in decoded["items"][0]["text"]
