from __future__ import annotations

import json

from cybrocamp_memory.cli import main


def test_graph_index_cli_writes_sanitized_graph_and_recall_graph(tmp_path):
    vault = tmp_path / "vault"
    graph_path = tmp_path / "sidecar" / "graph.jsonl"
    output = tmp_path / "recall_graph.json"
    (vault / "projects").mkdir(parents=True)
    (vault / "projects" / "graph.md").write_text(
        "alpha bridge\n\nbridge gamma",
        encoding="utf-8",
    )

    graph_code = main([
        "graph-index",
        "obsidian",
        "--vault",
        str(vault),
        "--output",
        str(graph_path),
        "--max-chars",
        "1200",
    ])
    recall_code = main([
        "recall-graph",
        "--graph",
        str(graph_path),
        "--query",
        "alpha",
        "--output",
        str(output),
        "--timestamp",
        "2026-04-29T00:00:00Z",
        "--max-depth",
        "2",
    ])

    assert graph_code == 0
    assert recall_code == 0
    raw_graph = graph_path.read_text(encoding="utf-8")
    assert "alpha bridge\n\nbridge gamma" not in raw_graph
    packet = json.loads(output.read_text(encoding="utf-8"))
    assert any(item["text"] == "[GRAPH_RECALL:alpha->bridge->gamma]" for item in packet["items"])
    assert packet["items"][0]["authority"] == "derived_summary"
