from __future__ import annotations

from cybrocamp_memory.eval_baseline import evaluate_baseline


def _hit(source_id: str, *, stale_flags=None, score=1):
    return {
        "source_id": source_id,
        "chunk_id": f"chunk-{source_id}",
        "score": score,
        "stale_flags": stale_flags or [],
    }


def test_eval_baseline_passes_for_expected_order():
    result = evaluate_baseline(
        hits=[_hit("strategy"), _hit("memory")],
        expected_source_order=["strategy", "memory"],
    )

    assert result.passed is True
    assert result.failures == []


def test_eval_baseline_fails_on_ranking_drift():
    result = evaluate_baseline(
        hits=[_hit("memory"), _hit("strategy")],
        expected_source_order=["strategy", "memory"],
    )

    assert result.passed is False
    assert "ranking_drift" in result.failures


def test_eval_baseline_fails_on_missing_or_stale_expected_hit():
    missing = evaluate_baseline(hits=[_hit("memory")], expected_source_order=["strategy"])
    stale = evaluate_baseline(hits=[_hit("strategy", stale_flags=["stale_source_hash"])], expected_source_order=["strategy"])

    assert missing.passed is False
    assert "missing_expected_source" in missing.failures
    assert stale.passed is False
    assert "stale_expected_hit" in stale.failures
