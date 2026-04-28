from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Sequence

from .schema import AuthorityClass, RecallPacket
from .search_index import build_search_terms


@dataclass(frozen=True, slots=True)
class MemPalaceResult:
    wing: str
    room: str
    drawer_id: str
    score: float
    source_hint: str | None = None
    content_preview: str | None = None

    @classmethod
    def from_raw(
        cls,
        *,
        wing: str,
        room: str,
        drawer_id: str,
        score: float,
        content: str | None = None,
        source_hint: str | None = None,
    ) -> "MemPalaceResult":
        return cls(
            wing=wing,
            room=room,
            drawer_id=drawer_id,
            score=score,
            source_hint=source_hint or _safe_source_hint(content or ""),
            content_preview=None,
        )


@dataclass(frozen=True, slots=True)
class MemPalaceComparison:
    category: str
    local_sources: list[str]
    mempalace_drawers: list[str]
    mempalace_sources: list[str]
    notes: list[str]
    authority: AuthorityClass = AuthorityClass.DERIVED_SUMMARY


def compare_with_mempalace(packet: RecallPacket, results: Sequence[MemPalaceResult]) -> MemPalaceComparison:
    local_sources = sorted({_source_key(item.evidence.source_uri, item.evidence.source_id) for item in packet.items})
    mem_sources = sorted({result.source_hint for result in results if result.source_hint})
    drawers = [result.drawer_id for result in sorted(results, key=lambda item: (item.score, item.drawer_id))]
    notes: list[str] = []
    if not packet.items and not results:
        category = "both_empty"
    elif packet.items and not results:
        category = "local_only"
    elif results and not packet.items:
        category = "mempalace_only"
    elif _overlaps(local_sources, mem_sources):
        category = "agree"
    else:
        category = "diverge"
        notes.append("no_overlapping_source_hints")
    return MemPalaceComparison(
        category=category,
        local_sources=local_sources,
        mempalace_drawers=drawers,
        mempalace_sources=mem_sources,
        notes=notes,
    )


def _source_key(source_uri: str, source_id: str | None) -> str:
    if source_id:
        return source_id
    if source_uri.startswith("obsidian://"):
        return source_uri.removeprefix("obsidian://")
    return source_uri


def _overlaps(local_sources: Sequence[str], mem_sources: Sequence[str]) -> bool:
    local_set = set(local_sources)
    mem_set = set(mem_sources)
    return bool(local_set.intersection(mem_set))


def _safe_source_hint(content: str) -> str | None:
    # Keep only sanitized terms as a weak source/topic hint. Never preserve raw drawer content.
    terms = build_search_terms(content)
    for term in sorted(terms, key=lambda value: (-len(value), value)):
        if re.search(r"[a-zа-я]", term, flags=re.IGNORECASE):
            return str(PurePosixPath(term))
    return None
