from __future__ import annotations

from .graph_index import TermGraph, recall_from_term_graph
from .schema import RecallItem, RecallPacket
from .search_index import SearchTermRecord, recall_from_search_terms


def hybrid_recall(
    records: list[SearchTermRecord],
    graph: TermGraph | None,
    query: str,
    *,
    timestamp: str,
    top_k: int = 8,
    include_graph: bool = True,
    graph_depth: int = 2,
    direct_k: int | None = None,
    graph_k: int | None = None,
) -> RecallPacket:
    """Return direct sanitized-term evidence first, then bounded graph associations.

    This is the first HippoCore-style orchestration surface. It does not answer
    questions; it assembles provenance-backed recall items. Direct evidence keeps
    its source authority. Graph paths remain `derived_summary` from Stage 5.
    """
    if top_k < 1:
        return RecallPacket(query=query, items=[])
    direct_packet = recall_from_search_terms(
        records,
        query,
        timestamp=timestamp,
        top_k=direct_k or top_k,
        include_stale=False,
    )
    items: list[RecallItem] = list(direct_packet.items)
    if include_graph and graph is not None:
        graph_packet = recall_from_term_graph(
            graph,
            query,
            timestamp=timestamp,
            top_k=graph_k or top_k,
            max_depth=graph_depth,
            include_stale=False,
        )
        items.extend(_dedupe_graph_items(items, graph_packet.items))
    return RecallPacket(query=direct_packet.query, items=items[:top_k])


def _dedupe_graph_items(existing: list[RecallItem], candidates: list[RecallItem]) -> list[RecallItem]:
    seen = {(item.evidence.source_id, item.evidence.chunk_id, item.text) for item in existing}
    result: list[RecallItem] = []
    for item in candidates:
        key = (item.evidence.source_id, item.evidence.chunk_id, item.text)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
