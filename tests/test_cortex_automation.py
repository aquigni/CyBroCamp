import json

from cybrocamp_memory.cortex_automation import (
    build_dream_archive_index,
    build_dream_context_bundle,
    build_event_ledger,
    build_nightly_cortex_eval,
    build_query_router_response,
)


def test_dream_context_bundle_reads_auto_promotion_audit_and_mempalace_deltas(tmp_path):
    audit = tmp_path / "auto-promotion-audit.md"
    audit.write_text(
        "# audit\n\n"
        "## 2026-05-09T09:04:38+03:00\n"
        "- promoted_count: 3\n"
        "- rooms_touched:\n"
        "  - `cybroswarm/research-source-graph` — `drawer_a`\n"
        "## 2026-05-09T21:11:53+03:00\n"
        "- promoted: 0\n"
        "- mempalace_rooms_touched: none\n",
        encoding="utf-8",
    )
    mempalace = tmp_path / "mempalace-deltas.json"
    mempalace.write_text(json.dumps({"drawers": [{"id": "drawer_a", "wing": "cybroswarm", "room": "research-source-graph"}]}), encoding="utf-8")

    bundle = build_dream_context_bundle(
        night="2026-05-10",
        timestamp="2026-05-10T03:00:00Z",
        auto_promotion_audit_path=audit,
        mempalace_deltas_path=mempalace,
    )

    assert bundle["schema_version"] == "cybrocamp.dream_context_bundle.v1"
    assert bundle["output_policy"]["canonical_writes"] is False
    assert bundle["auto_promotion"]["latest_entry"]["timestamp"] == "2026-05-09T21:11:53+03:00"
    assert bundle["mempalace_deltas"]["drawers"][0]["id"] == "drawer_a"
    assert bundle["authority_policy"]["retrieval_grants_authority"] is False


def test_event_ledger_links_cron_memory_and_dream_events_without_authority_promotion(tmp_path):
    dream = tmp_path / "dream.md"
    dream.write_text("# Dream\nnight: 2026-05-09\nreview_verdict: pass\narchive_artifact: x\n", encoding="utf-8")
    audit = tmp_path / "audit.md"
    audit.write_text("## 2026-05-09T21:11:53+03:00\n- promoted: 0\n- blockers: none\n", encoding="utf-8")

    ledger = build_event_ledger(
        timestamp="2026-05-10T03:00:00Z",
        dream_archive_paths=[dream],
        auto_promotion_audit_path=audit,
        cron_jobs=[{"job_id": "059", "name": "cybroswarm-dream-snapshot", "last_status": "ok"}],
    )

    assert ledger["schema_version"] == "cybrocamp.cortex_event_ledger.v1"
    event_types = {event["event_type"] for event in ledger["events"]}
    assert {"dream_archive", "auto_promotion_audit", "cron_job_state"} <= event_types
    for event in ledger["events"]:
        assert event["authority_class"] == "derived_summary"
        assert event["grants_permission"] is False


def test_query_router_merges_local_recall_ledger_and_memory_context():
    local_response = {
        "tool_response": {
            "recall_packet": {
                "items": [
                    {"evidence": {"source_id": "obsidian:strategy", "source_uri": "projects/cybroswarm/strategy.md"}, "score": 3.0}
                ],
                "policy_warnings": [],
            }
        }
    }
    ledger = {"events": [{"event_id": "evt1", "summary": "auto-promotion touched cybroswarm"}]}
    context = {"auto_promotion": {"latest_entry": {"timestamp": "2026-05-09T21:11:53+03:00"}}}

    routed = build_query_router_response(
        query="dream auto promotion cortex",
        timestamp="2026-05-10T03:00:00Z",
        local_recall_response=local_response,
        event_ledger=ledger,
        dream_context_bundle=context,
    )

    assert routed["schema_version"] == "cybrocamp.query_router_response.v1"
    assert routed["routes_used"] == ["local_recall", "event_ledger", "dream_context"]
    assert routed["items"][0]["source"] == "local_recall"
    assert routed["items"][1]["source"] == "event_ledger"
    assert routed["authority_policy"]["association_grants_facthood"] is False


def test_nightly_cortex_eval_requires_router_hits_and_archive_index_freshness(tmp_path):
    archive = tmp_path / "README.md"
    archive.write_text("- [[2026-05-09-phase2-bounded-consolidation]]\n", encoding="utf-8")
    router_responses = [
        {"query": "dream", "items": [{"source": "local_recall"}], "policy_warnings": []},
        {"query": "auto-promotion", "items": [], "policy_warnings": []},
    ]

    report = build_nightly_cortex_eval(
        night="2026-05-10",
        timestamp="2026-05-10T04:30:00Z",
        router_responses=router_responses,
        dream_archive_index_path=archive,
        expected_archive_entries=["2026-05-09-phase2-bounded-consolidation"],
    )

    assert report["schema_version"] == "cybrocamp.nightly_cortex_eval.v1"
    assert report["case_count"] == 2
    assert report["passed"] is False
    assert "no_router_hits" in report["failures"]
    assert report["archive_index"]["fresh"] is True
    assert report["output_policy"]["canonical_writes"] is False


def test_dream_archive_index_updates_current_entries_without_duplicate_links(tmp_path):
    dream_dir = tmp_path / "dreams"
    dream_dir.mkdir()
    (dream_dir / "2026-05-09-phase2-bounded-consolidation.md").write_text("# night 1\n", encoding="utf-8")
    (dream_dir / "2026-05-10-phase2-bounded-consolidation.md").write_text("# night 2\n", encoding="utf-8")
    existing = (
        "# CyBroSwarm shared dream archive\n\n"
        "## Current entries\n\n"
        "- [[2026-05-09-phase2-bounded-consolidation]] — existing description\n\n"
        "## Contradiction graph seed\n\n"
        "schema details stay here\n"
    )

    updated = build_dream_archive_index(dream_dir=dream_dir, existing_readme=existing)

    assert updated.count("[[2026-05-09-phase2-bounded-consolidation]]") == 1
    assert "[[2026-05-10-phase2-bounded-consolidation]]" in updated
    assert "existing description" in updated
    assert "dream proposal ≠ command" in updated
    assert "## Contradiction graph seed" in updated
    assert "schema details stay here" in updated
