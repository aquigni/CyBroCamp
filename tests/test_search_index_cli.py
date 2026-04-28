from __future__ import annotations

import json

from cybrocamp_memory.cli import main


def test_search_index_cli_writes_terms_without_raw_text_and_recall_index_finds(tmp_path):
    vault = tmp_path / "vault"
    index_path = tmp_path / "sidecar" / "search_terms.jsonl"
    output = tmp_path / "recall.json"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / "strategy.md").write_text(
        ("irrelevant " * 40) + "survival economics financial substrate CyBroSwarm",
        encoding="utf-8",
    )

    index_code = main([
        "search-index",
        "obsidian",
        "--vault",
        str(vault),
        "--output",
        str(index_path),
        "--max-chars",
        "1200",
    ])
    recall_code = main([
        "recall-index",
        "--index",
        str(index_path),
        "--query",
        "survival economics financial substrate CyBroSwarm",
        "--output",
        str(output),
        "--timestamp",
        "2026-04-29T00:00:00Z",
    ])

    assert index_code == 0
    assert recall_code == 0
    index_raw = index_path.read_text(encoding="utf-8")
    assert "survival economics financial substrate" not in index_raw
    packet = json.loads(output.read_text(encoding="utf-8"))
    assert packet["items"][0]["evidence"]["source_uri"] == "obsidian://projects/strategy.md"
