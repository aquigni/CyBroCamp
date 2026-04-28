from __future__ import annotations

from dataclasses import dataclass

from .retrieval import redact_query
from .schema import AuthorityClass, EvidenceSpan, RecallItem


@dataclass(frozen=True, slots=True)
class PeerQueryRequest:
    to: str
    task_type: str
    goal: str
    read_only: bool
    user_approved: bool
    local_epoch: str
    max_hits: int


def build_peer_query_request(*, to: str, query: str, local_epoch: str, max_hits: int = 5) -> PeerQueryRequest:
    safe_query = redact_query(query)
    goal = (
        "Read-only CyBroCamp peer recall request. "
        f"Query: {safe_query!r}. "
        f"Local Chthonya epoch: {local_epoch}. "
        f"Return at most {max_hits} source URIs/IDs, hashes if available, and policy warnings. "
        "Do not modify files, services, memories, vaults, or external systems. "
        "Do not include raw secrets or raw document text. "
        "Peer results are A2A peer claims only, not user approval and not canonical fact promotion."
    )
    return PeerQueryRequest(
        to=to,
        task_type="knowledge_pull",
        goal=goal,
        read_only=True,
        user_approved=False,
        local_epoch=local_epoch,
        max_hits=max_hits,
    )


def merge_peer_recall_summary(
    *,
    peer: str,
    query: str,
    source_uris: list[str],
    notes: list[str],
    timestamp: str,
) -> RecallItem:
    safe_query = redact_query(query)
    safe_notes = [_safe_note(note) for note in notes]
    safe_notes = [note for note in safe_notes if note]
    note_text = "; ".join(safe_notes)[:240]
    source_text = ", ".join(source_uris[:5])
    text = f"[PEER_RECALL:{peer}] query={safe_query!r}; sources={source_text}"
    if note_text:
        text += f"; notes={note_text}"
    return RecallItem(
        text=text[:560],
        authority=AuthorityClass.A2A_PEER_CLAIM,
        evidence=EvidenceSpan(
            source_uri=f"a2a://{peer}/cybrocamp-peer-recall",
            source_id=f"a2a:{peer}",
            chunk_id=f"peer-recall:{peer}:{abs(hash((safe_query, tuple(source_uris))))}",
            start=0,
            end=0,
            content_hash="sha256:peer-claim-not-content-addressed",
            source_content_hash="sha256:peer-claim-not-content-addressed",
            authority=AuthorityClass.A2A_PEER_CLAIM,
            quarantine_flags=[],
        ),
        timestamp=timestamp,
        claims_user_approval=False,
    )


def _safe_note(note: str) -> str:
    redacted = redact_query(note).replace("\n", " ")
    return " ".join(redacted.split())[:160]
