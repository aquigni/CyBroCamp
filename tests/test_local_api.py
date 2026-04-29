from __future__ import annotations

import json
from pathlib import Path

import pytest

from cybrocamp_memory.cli import main
from cybrocamp_memory.local_api import (
    build_api_bundle,
    build_api_status,
    build_query_response,
    run_local_api,
    validate_query_payload,
    write_api_bundle,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stage13"


def _runtime_artifact_dir(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / "current"
    artifact_dir.mkdir()
    (artifact_dir / "obsidian-search-terms.jsonl").write_text((FIXTURE_DIR / "search_terms.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    (artifact_dir / "obsidian-term-graph.jsonl").write_text((FIXTURE_DIR / "term_graph.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    (artifact_dir / "run-manifest.json").write_text(
        json.dumps({"schema_version": "cybrocamp.rebuild_run_manifest.v1", "epoch": "test", "record_counts": {"search_terms": 2}}, sort_keys=True),
        encoding="utf-8",
    )
    return artifact_dir


def test_api_status_reports_local_only_artifacts_and_safety_flags(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    status = build_api_status(
        artifact_dir=artifact_dir,
        timestamp="2026-04-29T00:00:00Z",
    )

    assert status["schema_version"] == "cybrocamp.local_api.status.v1"
    assert status["local_loopback_only"] is True
    assert status["canonical_writes"] is False
    assert status["network_calls_to_canonical_stores"] is False
    assert status["requires_human_approval_for_promotion"] is True
    assert status["artifacts"]["index"]["exists"] is True
    assert status["artifacts"]["graph"]["exists"] is True
    assert status["endpoints"] == ["GET /status", "POST /query"]


def test_query_response_wraps_hermes_tool_response_without_canonical_mutation(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    response = build_query_response(
        artifact_dir=artifact_dir,
        payload={"query": "stage13 hermes adapter eval", "top_k": 5},
        timestamp="2026-04-29T00:00:00Z",
    )

    assert response["schema_version"] == "cybrocamp.local_api.query_response.v1"
    assert response["canonical_writes"] is False
    assert response["network_calls_to_canonical_stores"] is False
    assert response["local_loopback_only"] is True
    assert response["tool_response"]["schema_version"] == "cybrocamp.hermes_tool_response.v1"
    first = response["tool_response"]["recall_packet"]["items"][0]
    assert first["evidence"]["source_id"] == "synthetic/cybrocamp-stage13.md"


def test_query_payload_is_bounded_and_sanitized():
    with pytest.raises(ValueError, match="query must be a non-empty string"):
        validate_query_payload({"query": "   "})
    with pytest.raises(ValueError, match="query is too long"):
        validate_query_payload({"query": "x" * 1001})
    with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
        validate_query_payload({"query": "ok", "top_k": 100})

    normalized = validate_query_payload({"query": "  survival economics  ", "top_k": "3", "include_graph": False})
    assert normalized == {"query": "survival economics", "top_k": 3, "include_graph": False}


def test_api_rejects_artifact_dir_inside_canonical_vault():
    with pytest.raises(ValueError, match="canonical vault"):
        build_api_status(
            artifact_dir="/opt/obs/vault/derived/cortex/current",
            timestamp="2026-04-29T00:00:00Z",
        )


def test_api_bundle_generates_loopback_user_systemd_service_outside_vault(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    bundle = build_api_bundle(
        repo_root=tmp_path / "repo",
        artifact_dir=artifact_dir,
        host="127.0.0.1",
        port=8765,
    )

    assert bundle["schema_version"] == "cybrocamp.local_api_bundle.v1"
    assert bundle["safety_envelope"]["canonical_writes"] is False
    assert bundle["safety_envelope"]["local_loopback_only"] is True
    assert "--host 127.0.0.1" in bundle["runner_script"]
    assert "--port 8765" in bundle["runner_script"]
    assert "cybrocamp_memory.cli local-api" in bundle["runner_script"]
    assert "NoNewPrivileges=true" in bundle["systemd_service"]


def test_api_bundle_rejects_non_loopback_host(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    with pytest.raises(ValueError, match="loopback"):
        build_api_bundle(
            repo_root=tmp_path / "repo",
            artifact_dir=artifact_dir,
            host="0.0.0.0",
            port=8765,
        )


def test_status_json_has_no_raw_text_or_preview_leakage(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    status = build_api_status(
        artifact_dir=artifact_dir,
        timestamp="2026-04-29T00:00:00Z",
    )
    raw = json.dumps(status, ensure_ascii=False, sort_keys=True)
    assert "text_preview" not in raw
    assert '"raw"' not in raw
    assert "api_key" not in raw.lower()


def test_manifest_status_summary_allowlists_safe_fields(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    (artifact_dir / "run-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "cybrocamp.rebuild_run.v1",
                "epoch": "vault-main-test",
                "timestamp": "2026-04-29T00:00:00Z",
                "source_label": "canonical-vault",
                "parameters": {"max_chars": 1200, "dangerous_note": "api_key=SHOULD_NOT_LEAK"},
                "record_counts": {"sources": 2, "bad": "api_key=SHOULD_NOT_LEAK"},
                "artifacts": {
                    "obsidian-search-terms.jsonl": {"bytes": 10, "sha256": "sha256:" + "a" * 64, "path": "/secret/path"},
                    "bad": {"raw": "api_key=SHOULD_NOT_LEAK"},
                },
                "raw": "api_key=SHOULD_NOT_LEAK",
            }
        ),
        encoding="utf-8",
    )
    status = build_api_status(artifact_dir=artifact_dir, timestamp="2026-04-29T00:00:01Z")
    raw = json.dumps(status, ensure_ascii=False, sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in raw
    assert "/secret/path" not in raw
    assert status["run_manifest"]["parameters"] == {"max_chars": 1200}
    assert status["run_manifest"]["artifacts"]["obsidian-search-terms.jsonl"]["sha256"] == "sha256:" + "a" * 64


def test_api_bundle_and_cli_outputs_reject_canonical_vault_writes(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    bundle = build_api_bundle(repo_root=tmp_path / "repo", artifact_dir=artifact_dir)
    with pytest.raises(ValueError, match="outside /opt/obs/vault"):
        write_api_bundle("/opt/obs/vault/projects/cybrocamp/local-api", bundle)
    with pytest.raises(ValueError, match="outside /opt/obs/vault"):
        main(
            [
                "local-api-status",
                "--artifact-dir",
                str(artifact_dir),
                "--output",
                "/opt/obs/vault/projects/cybrocamp/status.json",
                "--timestamp",
                "2026-04-29T00:00:00Z",
            ]
        )
    with pytest.raises(ValueError, match="outside /opt/obs/vault"):
        main(
            [
                "local-api-query",
                "--artifact-dir",
                str(artifact_dir),
                "--query",
                "stage13 hermes adapter eval",
                "--output",
                "/opt/obs/vault/projects/cybrocamp/query.json",
                "--timestamp",
                "2026-04-29T00:00:00Z",
            ]
        )


def test_run_local_api_rejects_non_loopback_and_invalid_port_before_binding(tmp_path):
    artifact_dir = _runtime_artifact_dir(tmp_path)
    with pytest.raises(ValueError, match="loopback"):
        run_local_api(artifact_dir=artifact_dir, host="0.0.0.0", port=8765)
    with pytest.raises(ValueError, match="port"):
        run_local_api(artifact_dir=artifact_dir, host="127.0.0.1", port=0)
