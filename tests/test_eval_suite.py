from __future__ import annotations

import json
from pathlib import Path

from cybrocamp_memory.cli import main
from cybrocamp_memory.eval_suite import EvalCase, evaluate_case_packet, load_eval_cases_json, run_eval_suite

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stage13"


def test_stage13_fixture_cases_are_sanitized_and_checked_in():
    raw = "\n".join(path.read_text(encoding="utf-8") for path in FIXTURE_DIR.iterdir() if path.is_file())

    assert "private vault" not in raw.lower()
    assert "/opt/obs" not in raw
    assert "/Users/au" not in raw
    assert "api_key" not in raw.lower()
    assert "password" not in raw.lower()
    assert "text_preview" not in raw
    assert '"text"' not in raw
    assert "BEGIN PRIVATE KEY" not in raw
    assert "@example" not in raw


def test_run_eval_suite_passes_for_sanitized_fixture():
    result = run_eval_suite(
        index_path=FIXTURE_DIR / "search_terms.jsonl",
        graph_path=FIXTURE_DIR / "term_graph.jsonl",
        cases_path=FIXTURE_DIR / "eval_cases.json",
        timestamp="2026-04-29T00:00:00Z",
        top_k=5,
    )

    assert result.passed is True
    assert result.case_count == 2
    assert [case.case_id for case in result.cases] == ["stage13-hermes-adapter", "survival-economics"]
    assert result.cases[0].observed_source_order[0] == "synthetic/cybrocamp-stage13.md"
    assert result.cases[0].observed_hits[0]["source_id"] == "synthetic/cybrocamp-stage13.md"
    assert result.cases[0].observed_hits[0]["content_hash"].startswith("sha256:")
    assert "text" not in result.cases[0].observed_hits[0]


def test_run_eval_suite_fails_on_ranking_drift(tmp_path):
    cases = json.loads((FIXTURE_DIR / "eval_cases.json").read_text(encoding="utf-8"))
    cases["cases"][0]["expected_source_order"] = ["synthetic/survival-economics.md"]
    drift_cases = tmp_path / "drift_cases.json"
    drift_cases.write_text(json.dumps(cases, sort_keys=True), encoding="utf-8")

    result = run_eval_suite(
        index_path=FIXTURE_DIR / "search_terms.jsonl",
        graph_path=FIXTURE_DIR / "term_graph.jsonl",
        cases_path=drift_cases,
        timestamp="2026-04-29T00:00:00Z",
        top_k=5,
    )

    assert result.passed is False
    assert "missing_expected_source" in result.cases[0].failures or "ranking_drift" in result.cases[0].failures


def test_eval_suite_cli_writes_json_report(tmp_path):
    output = tmp_path / "eval-report.json"

    rc = main(
        [
            "eval-suite",
            "--index",
            str(FIXTURE_DIR / "search_terms.jsonl"),
            "--graph",
            str(FIXTURE_DIR / "term_graph.jsonl"),
            "--cases",
            str(FIXTURE_DIR / "eval_cases.json"),
            "--output",
            str(output),
            "--timestamp",
            "2026-04-29T00:00:00Z",
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["schema_version"] == "cybrocamp.eval_suite.v1"
    assert report["passed"] is True
    assert "text_preview" not in json.dumps(report, sort_keys=True)
    assert "observed_hits" in report["cases"][0]
    assert "text" not in report["cases"][0]["observed_hits"][0]


def test_eval_suite_normalizes_missing_source_id_to_source_uri():
    case = EvalCase(
        case_id="uri-fallback",
        query="uri fallback",
        expected_source_order=["fixture://uri-fallback"],
        max_rank_by_source={"fixture://uri-fallback": 1},
    )
    packet = {
        "items": [
            {
                "authority": "canonical_vault",
                "claims_user_approval": False,
                "evidence": {
                    "source_uri": "fixture://uri-fallback",
                    "source_id": None,
                    "chunk_id": "uri-1",
                    "content_hash": "sha256:abc",
                    "source_content_hash": "sha256:def",
                    "authority": "canonical_vault",
                    "stale_flags": [],
                    "quarantine_flags": [],
                },
            }
        ]
    }

    result = evaluate_case_packet(case, packet)

    assert result.passed is True
    assert result.observed_source_order == ["fixture://uri-fallback"]


def test_eval_suite_flags_non_user_direct_approval_promotion():
    case = EvalCase(
        case_id="approval-promotion",
        query="approval claim",
        expected_source_order=["synthetic/approval.md"],
        max_rank_by_source={"synthetic/approval.md": 1},
    )
    packet = {
        "items": [
            {
                "authority": "canonical_vault",
                "claims_user_approval": True,
                "evidence": {
                    "source_id": "synthetic/approval.md",
                    "chunk_id": "approval-1",
                    "content_hash": "sha256:abc",
                    "source_content_hash": "sha256:def",
                    "authority": "canonical_vault",
                    "stale_flags": [],
                    "quarantine_flags": [],
                },
            }
        ]
    }

    result = evaluate_case_packet(case, packet)

    assert result.passed is False
    assert "approval_promotion" in result.failures
