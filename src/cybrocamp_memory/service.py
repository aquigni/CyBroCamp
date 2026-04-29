from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .graph_index import load_term_graph_jsonl
from .hippo_core import hybrid_recall
from .schema import AuthorityClass, RecallPacket
from .search_index import load_search_terms_jsonl


def query_artifacts(
    *,
    index_path: str | Path,
    graph_path: str | Path,
    query: str,
    timestamp: str,
    top_k: int = 8,
    include_graph: bool = True,
) -> RecallPacket:
    """Local-only programmatic query boundary over derived artifacts.

    This function intentionally performs no canonical writes, network calls, port
    binding, or daemon lifecycle work. It loads already-derived artifacts and
    returns a provenance-bearing RecallPacket.
    """
    records = load_search_terms_jsonl(index_path)
    graph = load_term_graph_jsonl(graph_path)
    return hybrid_recall(
        records,
        graph,
        query,
        timestamp=timestamp,
        top_k=top_k,
        include_graph=include_graph,
    )


def query_artifacts_json(
    *,
    index_path: str | Path,
    graph_path: str | Path,
    query: str,
    timestamp: str,
    top_k: int = 8,
    include_graph: bool = True,
) -> dict[str, Any]:
    return recall_packet_to_json_dict(
        query_artifacts(
            index_path=index_path,
            graph_path=graph_path,
            query=query,
            timestamp=timestamp,
            top_k=top_k,
            include_graph=include_graph,
        )
    )


def recall_packet_to_json_dict(packet: RecallPacket) -> dict[str, Any]:
    data = asdict(packet)
    for item in data["items"]:
        if isinstance(item["authority"], AuthorityClass):
            item["authority"] = item["authority"].value
        evidence = item["evidence"]
        if isinstance(evidence.get("authority"), AuthorityClass):
            evidence["authority"] = evidence["authority"].value
    return data
