from __future__ import annotations

from cybrocamp_memory.chunks import ChunkRecord
from cybrocamp_memory.graph_index import build_term_graph
from cybrocamp_memory.hippo_core import hybrid_recall
from cybrocamp_memory.manifest import SourceRecord
from cybrocamp_memory.schema import AuthorityClass
from cybrocamp_memory.search_index import search_terms


def _source(source_id: str) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        uri=f"obsidian://{source_id}.md",
        authority=AuthorityClass.CANONICAL_VAULT,
        epoch="fixture",
        content_hash=f"sha256:{source_id}",
        created_at="2026-04-29T00:00:00Z",
    )


def _chunk(text: str, source_id: str) -> ChunkRecord:
    return ChunkRecord.from_text(_source(source_id), 0, text, 0, len(text.encode("utf-8")))


def test_hybrid_recall_ranks_direct_evidence_before_graph_association():
    direct = _chunk("survival economics financial substrate cybroswarm", "strategy")
    bridge = _chunk("cybroswarm server subscriptions", "ops")
    records = search_terms([direct, bridge])
    graph = build_term_graph(records)

    packet = hybrid_recall(records, graph, "survival economics cybroswarm", timestamp="2026-04-29T00:00:00Z", top_k=4)

    assert packet.items[0].authority is AuthorityClass.CANONICAL_VAULT
    assert packet.items[0].evidence.source_id == "strategy"
    assert any(item.authority is AuthorityClass.DERIVED_SUMMARY for item in packet.items[1:])
    assert packet.policy_warnings == []


def test_hybrid_recall_can_disable_graph_paths():
    direct = _chunk("alpha beta", "direct")
    bridge = _chunk("beta gamma", "bridge")
    records = search_terms([direct, bridge])
    graph = build_term_graph(records)

    packet = hybrid_recall(records, graph, "alpha", timestamp="2026-04-29T00:00:00Z", include_graph=False)

    assert packet.items
    assert all(not item.text.startswith("[GRAPH_RECALL:") for item in packet.items)


def test_hippo_query_cli_combines_index_and_graph(tmp_path):
    from cybrocamp_memory.cli import main
    from cybrocamp_memory.graph_index import write_term_graph_jsonl
    from cybrocamp_memory.search_index import write_search_terms_jsonl
    import json

    chunk = _chunk("survival economics financial substrate cybroswarm", "strategy")
    records = search_terms([chunk])
    graph = build_term_graph(records)
    index_path = tmp_path / "index.jsonl"
    graph_path = tmp_path / "graph.jsonl"
    output = tmp_path / "packet.json"
    write_search_terms_jsonl(index_path, records)
    write_term_graph_jsonl(graph_path, graph.edges)

    code = main([
        "hippo-query",
        "--index", str(index_path),
        "--graph", str(graph_path),
        "--query", "survival economics cybroswarm",
        "--output", str(output),
        "--timestamp", "2026-04-29T00:00:00Z",
    ])

    assert code == 0
    packet = json.loads(output.read_text(encoding="utf-8"))
    assert packet["items"][0]["evidence"]["source_id"] == "strategy"
    assert "text_preview" not in output.read_text(encoding="utf-8")
