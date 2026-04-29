from __future__ import annotations

import json
from pathlib import Path

from cybrocamp_memory.hermes_adapter import build_hermes_tool_response

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stage13"


def test_hermes_tool_adapter_returns_safe_local_response():
    response = build_hermes_tool_response(
        index_path=FIXTURE_DIR / "search_terms.jsonl",
        graph_path=FIXTURE_DIR / "term_graph.jsonl",
        query="stage13 hermes adapter eval",
        timestamp="2026-04-29T00:00:00Z",
        top_k=5,
    )

    assert response["schema_version"] == "cybrocamp.hermes_tool_response.v1"
    assert response["canonical_writes"] is False
    assert response["network_calls"] is False
    assert response["requires_human_approval_for_promotion"] is True
    assert response["recall_packet"]["items"][0]["evidence"]["source_id"] == "synthetic/cybrocamp-stage13.md"


def test_hermes_tool_adapter_omits_preview_and_raw_text_fields():
    response = build_hermes_tool_response(
        index_path=FIXTURE_DIR / "search_terms.jsonl",
        graph_path=FIXTURE_DIR / "term_graph.jsonl",
        query="survival economics subscriptions",
        timestamp="2026-04-29T00:00:00Z",
    )
    raw = json.dumps(response, ensure_ascii=False, sort_keys=True)

    assert "text_preview" not in raw
    assert '"raw"' not in raw
    assert "api_key" not in raw.lower()
    assert response["recall_packet"]["items"][0]["authority"] == "canonical_vault"


def test_hermes_tool_adapter_rejects_missing_paths(tmp_path):
    try:
        build_hermes_tool_response(
            index_path=tmp_path / "missing-index.jsonl",
            graph_path=FIXTURE_DIR / "term_graph.jsonl",
            query="stage13",
            timestamp="2026-04-29T00:00:00Z",
        )
    except FileNotFoundError as exc:
        assert "missing artifact path" in str(exc)
    else:
        raise AssertionError("expected adapter to fail closed on missing artifact paths")


def test_hermes_tool_adapter_rejects_canonical_vault_paths():
    try:
        build_hermes_tool_response(
            index_path="/opt/obs/vault/derived/search_terms.jsonl",
            graph_path=FIXTURE_DIR / "term_graph.jsonl",
            query="stage13",
            timestamp="2026-04-29T00:00:00Z",
        )
    except ValueError as exc:
        assert "canonical vault" in str(exc)
    else:
        raise AssertionError("expected adapter to reject artifact paths inside canonical vault")
