from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable


class AuthorityClass(StrEnum):
    USER_DIRECT = "user_direct"
    CANONICAL_VAULT = "canonical_vault"
    CANONICAL_MEMPALACE = "canonical_mempalace"
    LOCAL_MEMPALACE = "local_mempalace"
    A2A_PEER_CLAIM = "a2a_peer_claim"
    CRON_RESULT = "cron_result"
    DERIVED_SUMMARY = "derived_summary"
    EXTERNAL_SOURCE = "external_source"
    PAYLOAD_UNTRUSTED = "payload_untrusted"


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    source_uri: str
    start: int
    end: int
    content_hash: str
    source_id: str | None = None
    chunk_id: str | None = None
    authority: AuthorityClass | None = None
    quarantine_flags: list[str] = field(default_factory=list)
    source_content_hash: str | None = None
    stale_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.source_uri:
            raise ValueError("evidence span requires source_uri")
        if self.start < 0 or self.end < self.start:
            raise ValueError("evidence span requires 0 <= start <= end")
        if not self.content_hash:
            raise ValueError("evidence span requires content_hash")


@dataclass(frozen=True, slots=True)
class RecallItem:
    text: str
    authority: AuthorityClass
    evidence: EvidenceSpan
    timestamp: str
    claims_user_approval: bool = False

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("recall item requires text")
        if not self.timestamp:
            raise ValueError("recall item requires timestamp")


@dataclass(frozen=True, slots=True)
class RecallPacket:
    query: str
    items: list[RecallItem]
    policy_warnings: list[str] = field(init=False)

    def __post_init__(self) -> None:
        if not self.query:
            raise ValueError("recall packet requires query")
        object.__setattr__(self, "policy_warnings", _policy_warnings(self.items))


def _policy_warnings(items: Iterable[RecallItem]) -> list[str]:
    item_list = list(items)
    warnings: list[str] = []
    for item in item_list:
        if item.claims_user_approval and item.authority is not AuthorityClass.USER_DIRECT:
            if "non_user_direct_approval_claim" not in warnings:
                warnings.append("non_user_direct_approval_claim")
        if item.evidence.quarantine_flags:
            if "quarantined_evidence" not in warnings:
                warnings.append("quarantined_evidence")
        if item.evidence.stale_flags:
            if "stale_evidence" not in warnings:
                warnings.append("stale_evidence")
    if not item_list and "no_valid_hits" not in warnings:
        warnings.append("no_valid_hits")
    return warnings
