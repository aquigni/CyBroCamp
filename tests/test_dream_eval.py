from cybrocamp_memory.dream_eval import build_dream_review


def test_dream_review_preserves_authority_invariants_and_diagnostics_only():
    packet = {
        "schema": "cybroswarm.shared_dream_packet.v0",
        "authority_policy": {
            "retrieval_is_authority": False,
            "peer_claim_is_approval": False,
            "dream_proposal_is_command": False,
            "repetition_is_facthood": False,
        },
        "metrics": {
            "mempalace_available": True,
            "hindsight_available": True,
            "a2a_latency_ms": {"mac0sh": 74000, "debi0": 500},
            "task_blocked": 1,
            "task_failed": 0,
            "local_error": 0,
        },
        "sisters": {
            "mac0sh": {"contribution_state": "received", "authority_class": "a2a_peer_claim"},
            "debi0": {"contribution_state": "received", "role": "bounded_readonly"},
        },
    }

    review = build_dream_review(packet, timestamp="2026-05-07T16:00:00Z").to_json_dict()

    assert review["schema_version"] == "cybrocamp.dream_review.v1"
    assert review["output_policy"]["canonical_writes"] is False
    assert review["output_policy"]["network_calls"] is False
    assert review["output_policy"]["diagnostic_only"] is True
    assert review["authority_policy"]["retrieval_grants_authority"] is False
    assert review["authority_policy"]["peer_claim_grants_approval"] is False
    assert review["authority_policy"]["dream_proposal_grants_command"] is False
    assert review["diagnostics"]["metrics_mode"] == "diagnostic_only"
    assert review["verdict"] == "pass"


def test_dream_review_blocks_debi0_role_expansion_and_service_identity_promotion():
    packet = {
        "schema": "cybroswarm.shared_dream_packet.v0",
        "authority_policy": {
            "retrieval_is_authority": False,
            "peer_claim_is_approval": False,
            "dream_proposal_is_command": False,
            "repetition_is_facthood": False,
        },
        "sisters": {
            "debi0": {"contribution_state": "received", "role": "canonical_builder"},
        },
        "promotion_candidates": [
            {"kind": "service_identity", "subject": "mac0sh", "action": "promote", "human_approved": False},
        ],
    }

    review = build_dream_review(packet, timestamp="2026-05-07T16:00:00Z").to_json_dict()

    assert review["verdict"] == "revise"
    assert "debi0_role_expansion_blocked" in review["diagnostics"]["warnings"]
    assert "service_identity_promotion_requires_human_approval" in review["diagnostics"]["warnings"]
    assert review["authority_policy"]["service_identity_promotion_human_gated"] is True


def test_dream_review_redacts_secret_like_metric_values():
    packet = {
        "schema": "cybroswarm.shared_dream_packet.v0",
        "authority_policy": {
            "retrieval_is_authority": False,
            "peer_claim_is_approval": False,
            "dream_proposal_is_command": False,
            "repetition_is_facthood": False,
        },
        "metrics": {"note": "tok" + "en=abc123456789 at /home/user/private/file"},
    }

    review = build_dream_review(packet, timestamp="2026-05-07T16:00:00Z").to_json_dict()

    serialized = str(review)
    assert "abc123456789" not in serialized
    assert "/home/user/private/file" not in serialized
    assert "[REDACTED_SECRET]" in serialized


def test_dream_review_redacts_non_secret_paths():
    packet = {
        "schema": "cybroswarm.shared_dream_packet.v0",
        "authority_policy": {
            "retrieval_is_authority": False,
            "peer_claim_is_approval": False,
            "dream_proposal_is_command": False,
            "repetition_is_facthood": False,
        },
        "metrics": {"path": "/home/user/private/file"},
    }

    review = build_dream_review(packet, timestamp="2026-05-07T16:00:00Z").to_json_dict()

    serialized = str(review)
    assert "/home/user/private/file" not in serialized
    assert "[REDACTED_PATH]" in serialized


def test_dream_review_redacts_values_under_secret_like_keys():
    packet = {
        "schema": "cybroswarm.shared_dream_packet.v0",
        "authority_policy": {
            "retrieval_is_authority": False,
            "peer_claim_is_approval": False,
            "dream_proposal_is_command": False,
            "repetition_is_facthood": False,
        },
        "metrics": {
            "token": "abc123456789",
            "nested": {"api_key": "sk-test-123456"},
            "mixed": "pass" + "word=correct horse battery staple and tok" + "en=second",
            "cookie": "sessionid=abc def",
        },
    }

    review = build_dream_review(packet, timestamp="2026-05-07T16:00:00Z").to_json_dict()

    serialized = str(review)
    for leaked in ["abc123456789", "sk-test-123456", "correct", "horse", "battery", "staple", "second", "sessionid", "abc def"]:
        assert leaked not in serialized
    assert serialized.count("[REDACTED_SECRET]") >= 4
