from __future__ import annotations

from pathlib import Path
from typing import Any

from .service import query_artifacts_json

HERMES_TOOL_RESPONSE_SCHEMA_VERSION = "cybrocamp.hermes_tool_response.v1"
_CANONICAL_VAULT_ROOT = Path("/opt/obs/vault")


def build_hermes_tool_response(
    *,
    index_path: str | Path,
    graph_path: str | Path,
    query: str,
    timestamp: str,
    top_k: int = 8,
    include_graph: bool = True,
) -> dict[str, Any]:
    """Build a safe Hermes-local tool response from derived CyBroCamp artifacts.

    The adapter deliberately stays import-only: no network calls, no daemon, no
    port binding, and no canonical memory writes. Promotion of any recall item
    remains a separate audited action requiring explicit H0st approval.
    """
    index = _validated_artifact_path(index_path)
    graph = _validated_artifact_path(graph_path)
    packet = query_artifacts_json(
        index_path=index,
        graph_path=graph,
        query=query,
        timestamp=timestamp,
        top_k=top_k,
        include_graph=include_graph,
    )
    return {
        "schema_version": HERMES_TOOL_RESPONSE_SCHEMA_VERSION,
        "tool_name": "cybrocamp.memory.query",
        "canonical_writes": False,
        "network_calls": False,
        "safe_for_context": True,
        "requires_human_approval_for_promotion": True,
        "recall_packet": packet,
    }


def _validated_artifact_path(path: str | Path) -> Path:
    candidate = Path(path)
    resolved = candidate.resolve(strict=False)
    vault = _CANONICAL_VAULT_ROOT.resolve(strict=False)
    if resolved == vault or vault in resolved.parents:
        raise ValueError("Hermes adapter artifact paths must not point inside the canonical vault")
    if not candidate.exists():
        raise FileNotFoundError(f"missing artifact path: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"artifact path is not a file: {candidate}")
    return candidate
