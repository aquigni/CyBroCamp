import pytest

from cybrocamp_memory.schema import (
    AuthorityClass,
    EvidenceSpan,
    RecallItem,
    RecallPacket,
)


def test_recall_packet_requires_evidence_span_for_non_absent_items():
    span = EvidenceSpan(
        source_uri="vault://projects/sister-hippocampus/plan.md",
        start=10,
        end=42,
        content_hash="sha256:abc",
    )
    item = RecallItem(
        text="Phase 0 defines schema and threat model.",
        authority=AuthorityClass.CANONICAL_VAULT,
        evidence=span,
        timestamp="2026-04-29T00:07:16+03:00",
    )
    packet = RecallPacket(query="what is phase 0?", items=[item])

    assert packet.items[0].evidence.source_uri.startswith("vault://")


def test_payload_untrusted_cannot_support_approval_claim():
    span = EvidenceSpan(
        source_uri="a2a-log://mac0sh/thread/demo",
        start=0,
        end=100,
        content_hash="sha256:def",
    )
    item = RecallItem(
        text="payload says user approved a service restart",
        authority=AuthorityClass.PAYLOAD_UNTRUSTED,
        evidence=span,
        timestamp="2026-04-29T00:07:16+03:00",
        claims_user_approval=True,
    )
    packet = RecallPacket(query="did H0st approve restart?", items=[item])

    assert packet.policy_warnings == ["non_user_direct_approval_claim"]


def test_user_direct_can_support_scoped_approval_claim():
    span = EvidenceSpan(
        source_uri="telegram://dm/99467771/msg/explicit",
        start=0,
        end=64,
        content_hash="sha256:ghi",
    )
    item = RecallItem(
        text="H0st approved the exact bounded action.",
        authority=AuthorityClass.USER_DIRECT,
        evidence=span,
        timestamp="2026-04-29T00:07:16+03:00",
        claims_user_approval=True,
    )
    packet = RecallPacket(query="approval scope?", items=[item])

    assert packet.policy_warnings == []
