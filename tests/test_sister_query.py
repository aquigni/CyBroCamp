from __future__ import annotations

from cybrocamp_memory.schema import AuthorityClass
from cybrocamp_memory.sister_query import build_peer_query_request, merge_peer_recall_summary


def test_peer_query_request_is_readonly_and_redacts_secret_query():
    request = build_peer_query_request(
        to="mac0sh",
        query="token=SECRET survival economics",
        local_epoch="vault-main-abc123",
        max_hits=3,
    )

    assert request.to == "mac0sh"
    assert request.task_type == "knowledge_pull"
    assert request.read_only is True
    assert request.user_approved is False
    assert "SECRET" not in request.goal
    assert "[REDACTED]" in request.goal
    assert "Do not modify" in request.goal


def test_peer_result_summary_is_peer_claim_not_user_approval():
    summary = merge_peer_recall_summary(
        peer="mac0sh",
        query="survival economics",
        source_uris=["obsidian://projects/cybroswarm/strategy.md"],
        notes=["peer found matching strategy note"],
        timestamp="2026-04-29T00:00:00Z",
    )

    assert summary.authority is AuthorityClass.A2A_PEER_CLAIM
    assert summary.claims_user_approval is False
    assert summary.evidence.authority is AuthorityClass.A2A_PEER_CLAIM
    assert "mac0sh" in summary.text


def test_peer_summary_omits_raw_peer_text_and_limits_notes():
    long_note = "x" * 2000
    summary = merge_peer_recall_summary(
        peer="mac0sh",
        query="q",
        source_uris=["obsidian://safe.md"],
        notes=[long_note, "api_key=SECRET"],
        timestamp="2026-04-29T00:00:00Z",
    )

    assert "SECRET" not in summary.text
    assert len(summary.text) < 600
