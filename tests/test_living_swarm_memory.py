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
    assert hygiene["gate"] == "sister_reviewed_low_risk_proposal"
    assert hygiene["executable"] is False
    assert packet["authority_policy"]["service_identity_promotion_human_gated"] is True


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


def test_living_memory_packet_writer_rejects_canonical_vault_output(tmp_path):
    packet = build_living_memory_packet(night="2026-05-08")

    with pytest.raises(ValueError, match="must not be inside canonical vault"):
        write_living_memory_packet_json("/opt/obs/vault/projects/cybroswarm/dreams/unsafe.json", packet)

    safe_path = tmp_path / "packet.json"
    write_living_memory_packet_json(safe_path, packet)
    assert safe_path.exists()
