import pytest

from cybrocamp_memory.living_swarm_memory import build_living_memory_packet, write_living_memory_packet_json


def test_living_memory_packet_indexes_archive_and_sister_contributions():
    packet = build_living_memory_packet(
        night="2026-05-08",
        phase_state="phase2_active_bounded",
        jobs={
            "snapshot": {"id": "j1", "status": "ok"},
            "sister_contributions": {"id": "j2", "status": "ok"},
            "outcomes_review": {"id": "j4", "status": "ok", "verdict": "pass"},
        },
        sisters={
            "mac0sh": {"state": "received", "task_id": "task_m", "authority_class": "a2a_peer_claim"},
            "debi0": {"state": "received", "task_id": "task_d", "role": "bounded_readonly"},
        },
        artifacts={"obsidian": ["projects/cybroswarm/dreams/2026-05-08-consolidation.md"]},
    ).to_json_dict()

    assert packet["schema_version"] == "cybrocamp.living_swarm_memory.v1"
    assert packet["output_policy"]["canonical_writes"] is False
    assert packet["output_policy"]["network_calls"] is True
    assert packet["output_policy"]["approval_state_writes"] is False
    assert packet["output_policy"]["service_mutations"] is False
    assert packet["output_policy"]["diagnostic_only"] is False
    assert packet["archive_entry"]["health_metrics_mode"] == "bounded_live"
    assert packet["archive_entry"]["night"] == "2026-05-08"
    assert packet["archive_entry"]["jobs"]["outcomes_review"]["verdict"] == "pass"
    assert packet["sister_contributions"]["mac0sh"]["authority_class"] == "a2a_peer_claim"
    assert packet["sister_contributions"]["debi0"]["role"] == "bounded_readonly"


def test_living_memory_packet_builds_contradiction_candidates_without_fact_promotion():
    packet = build_living_memory_packet(
        night="2026-05-08",
        contradiction_candidates=[
            {
                "subject": "debi0 capability",
                "claim_a": {"text": "receipt proves only acknowledgement", "authority_class": "protocol"},
                "claim_b": {"text": "receipt proves full reasoning", "authority_class": "peer_claim"},
            }
        ],
    ).to_json_dict()

    graph = packet["contradiction_graph"]
    assert len(graph) == 1
    assert graph[0]["status"] == "candidate"
    assert graph[0]["resolution_policy"] == "do not promote either side without evidence/authority gate"
    assert packet["authority_policy"]["repetition_grants_facthood"] is False


def test_living_memory_packet_keeps_service_identity_promotion_human_gated():
    packet = build_living_memory_packet(
        night="2026-05-08",
        promotion_candidates=[
            {"kind": "service_identity", "subject": "mac0sh", "action": "promote", "sister_reviewed": True},
            {"kind": "memory_hygiene", "subject": "duplicate dream note", "action": "propose_dedupe"},
        ],
    ).to_json_dict()

    promotions = packet["promotion_queue"]
    service = [p for p in promotions if p["kind"] == "service_identity"][0]
    hygiene = [p for p in promotions if p["kind"] == "memory_hygiene"][0]
    assert service["gate"] == "human_required"
    assert service["executable"] is False
    assert hygiene["gate"] == "sister_reviewed_low_risk"
    assert hygiene["executable"] is True
    assert packet["authority_policy"]["service_identity_promotion_human_gated"] is True


def test_living_memory_packet_blocks_unknown_and_risky_promotion_kinds_by_default():
    packet = build_living_memory_packet(
        night="2026-05-08",
        promotion_candidates=[
            {"kind": "public_post", "subject": "channel", "action": "send"},
            {"kind": "kg_mutation", "subject": "mempalace", "action": "write_fact"},
            {"kind": "destructive_memory_cleanup", "subject": "old notes", "action": "delete"},
            {"kind": "unknown_future_kind", "subject": "future", "action": "execute"},
        ],
    ).to_json_dict()

    for promotion in packet["promotion_queue"]:
        assert promotion["gate"] == "human_required"
        assert promotion["executable"] is False


def test_living_memory_packet_redacts_secret_like_values_and_absolute_paths():
    packet = build_living_memory_packet(
        night="2026-05-08",
        health_metrics={
            "note": "tok" + "en=abc123456 at /home/user/private/file",
            "api_key": "sk-test-123456",
        },
    ).to_json_dict()

    serialized = str(packet)
    assert "abc123456" not in serialized
    assert "sk-test-123456" not in serialized
    assert "/home/user/private/file" not in serialized
    assert "[REDACTED_SECRET]" in serialized


def test_living_memory_packet_redacts_tuple_nested_secret_and_path_values():
    packet = build_living_memory_packet(
        night="2026-05-08",
        health_metrics={"items": ("tok" + "en=LEAKME", "/home/user/private/file")},
    ).to_json_dict()

    serialized = str(packet)
    assert "LEAKME" not in serialized
    assert "/home/user/private/file" not in serialized
    assert "[REDACTED_SECRET]" in serialized
    assert "[REDACTED_PATH]" in serialized
    assert isinstance(packet["health_metrics"]["items"], list)


def test_living_memory_packet_normalizes_service_identity_kind_variants():
    packet = build_living_memory_packet(
        night="2026-05-08",
        promotion_candidates=[{"kind": " Service_Identity ", "subject": "mac0sh", "action": "promote"}],
    ).to_json_dict()

    promotion = packet["promotion_queue"][0]
    assert promotion["kind"] == "service_identity"
    assert promotion["gate"] == "human_required"
    assert promotion["executable"] is False


def test_h0st_approved_bounded_identity_and_service_promotions_require_safety_fields():
    packet = build_living_memory_packet(
        night="2026-05-08",
        promotion_candidates=[
            {
                "kind": "mac0sh_identity_alias_normalization",
                "subject": "mac0sh identity alias",
                "action": "normalize_alias",
                "h0st_approved": True,
                "architecture_review": "pass",
                "rollback": "restore previous alias mapping",
                "notify_h0st": True,
            },
            {
                "kind": "cybrocamp_service_mutation",
                "subject": "cybrocamp internal service",
                "action": "update_repo_managed_service_contract",
                "h0st_approved": True,
                "architecture_review": "pass",
                "rollback": "revert repo commit",
                "repo_commit_required": True,
            },
            {
                "kind": "service_identity",
                "subject": "identity without notification",
                "action": "promote",
                "h0st_approved": True,
                "architecture_review": "pass",
                "rollback": "revert promotion",
            },
        ],
    ).to_json_dict()

    alias, service, missing_notice = packet["promotion_queue"]
    assert alias["gate"] == "h0st_approved_bounded"
    assert alias["executable"] is True
    assert alias["notify_h0st_required"] is True
    assert service["gate"] == "h0st_approved_bounded"
    assert service["repo_commit_required"] is True
    assert service["executable"] is True
    assert missing_notice["gate"] == "human_required"
    assert missing_notice["executable"] is False


def test_h0st_approved_bounded_promotions_fail_closed_without_architecture_review_or_rollback():
    packet = build_living_memory_packet(
        night="2026-05-08",
        promotion_candidates=[
            {
                "kind": "mempalace_mutation",
                "subject": "dedupe drawer",
                "action": "delete_duplicate",
                "h0st_approved": True,
                "rollback": "restore drawer from backup",
            },
            {
                "kind": "approval_boundary",
                "subject": "boundary",
                "action": "promote",
                "h0st_approved": True,
                "architecture_review": "pass",
            },
        ],
    ).to_json_dict()

    for promotion in packet["promotion_queue"]:
        assert promotion["gate"] == "human_required"
        assert promotion["executable"] is False


def test_living_memory_packet_writer_rejects_canonical_vault_output(tmp_path):
    packet = build_living_memory_packet(night="2026-05-08")

    with pytest.raises(ValueError, match="must not be inside canonical vault"):
        write_living_memory_packet_json("/opt/obs/vault/projects/cybroswarm/dreams/unsafe.json", packet)

    safe_path = tmp_path / "packet.json"
    write_living_memory_packet_json(safe_path, packet)
    assert safe_path.exists()
