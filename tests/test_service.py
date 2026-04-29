from __future__ import annotations

import json

from cybrocamp_memory.graph_index import build_term_graph, write_term_graph_jsonl
from cybrocamp_memory.schema import AuthorityClass
from cybrocamp_memory.search_index import SearchTermRecord, search_terms, write_search_terms_jsonl
from cybrocamp_memory.service import query_artifacts, query_artifacts_json


def _record(*terms: str, source_id: str = "strategy") -> SearchTermRecord:
    return SearchTermRecord(
        source_id=source_id,
        source_uri=f"obsidian://{source_id}.md",
        chunk_id=f"chunk-{source_id}",
        chunk_index=0,
        content_hash=f"sha256:chunk-{source_id}",
        source_content_hash=f"sha256:{source_id}",
        span_start=0,
        span_end=10,
        text_preview="",
        authority=AuthorityClass.CANONICAL_VAULT,
        terms=list(terms),
    )


def test_query_artifacts_returns_recallpacket_with_evidence_without_writes(tmp_path):
    index_path = tmp_path / "index.jsonl"
    graph_path = tmp_path / "graph.jsonl"
    records = [_record("survival", "economics", "cybroswarm")]
    write_search_terms_jsonl(index_path, records)
    write_term_graph_jsonl(graph_path, build_term_graph(records).edges)

    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    packet = query_artifacts(index_path=index_path, graph_path=graph_path, query="survival economics", timestamp="2026-04-29T00:00:00Z")
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    assert before == after
    assert packet.items
    assert packet.items[0].evidence.source_id == "strategy"
    assert packet.items[0].authority is AuthorityClass.CANONICAL_VAULT


def test_query_artifacts_json_preserves_policy_and_omits_preview_fields(tmp_path):
    index_path = tmp_path / "index.jsonl"
    graph_path = tmp_path / "graph.jsonl"
    records = [_record("alpha", "beta")]
    write_search_terms_jsonl(index_path, records)
    write_term_graph_jsonl(graph_path, build_term_graph(records).edges)

    data = query_artifacts_json(index_path=index_path, graph_path=graph_path, query="alpha", timestamp="2026-04-29T00:00:00Z")
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)

    assert data["items"][0]["evidence"]["source_id"] == "strategy"
    assert "policy_warnings" in data
    assert "text_preview" not in raw
