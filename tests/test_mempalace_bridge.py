from __future__ import annotations

from cybrocamp_memory.mempalace_bridge import MemPalaceResult, compare_with_mempalace
from cybrocamp_memory.schema import AuthorityClass, EvidenceSpan, RecallItem, RecallPacket


def _packet(source_uri: str = "obsidian://projects/cybroswarm/strategy.md") -> RecallPacket:
    return RecallPacket(
        query="survival economics cybroswarm",
        items=[
            RecallItem(
                text="[INDEXED_RECALL:source]",
                authority=AuthorityClass.CANONICAL_VAULT,
                evidence=EvidenceSpan(
                    source_uri=source_uri,
                    source_id=source_uri.removeprefix("obsidian://"),
                    chunk_id="chunk-1",
                    start=0,
                    end=10,
                    content_hash="sha256:chunk",
                    source_content_hash="sha256:source",
                    authority=AuthorityClass.CANONICAL_VAULT,
                ),
                timestamp="2026-04-29T00:00:00Z",
            )
        ],
    )


def test_mempalace_comparison_detects_source_agreement():
    comparison = compare_with_mempalace(
        _packet(),
        [MemPalaceResult(wing="cybroswarm", room="strategy", drawer_id="drawer1", score=0.1, source_hint="projects/cybroswarm/strategy.md")],
    )

    assert comparison.category == "agree"
    assert comparison.local_sources == ["projects/cybroswarm/strategy.md"]
    assert comparison.mempalace_drawers == ["drawer1"]


def test_mempalace_comparison_detects_divergence_without_promoting_authority():
    comparison = compare_with_mempalace(
        _packet("obsidian://projects/cybrocamp/memory-sidecar-phase0-kickoff.md"),
        [MemPalaceResult(wing="cybroswarm", room="strategy", drawer_id="drawer1", score=0.1, source_hint="projects/cybroswarm/strategy.md")],
    )

    assert comparison.category == "diverge"
    assert comparison.authority is AuthorityClass.DERIVED_SUMMARY
    assert "no_overlapping_source_hints" in comparison.notes


def test_mempalace_result_redacts_content_and_keeps_metadata_only():
    result = MemPalaceResult.from_raw(wing="x", room="y", drawer_id="d", score=0.2, content="api_key=SECRET strategy path")

    assert result.content_preview is None
    assert result.source_hint == "strategy"
