from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .eval_baseline import evaluate_baseline
from .service import query_artifacts_json

EVAL_CASES_SCHEMA_VERSION = "cybrocamp.eval_cases.v1"
EVAL_SUITE_SCHEMA_VERSION = "cybrocamp.eval_suite.v1"


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    query: str
    expected_source_order: list[str]
    max_rank_by_source: dict[str, int]


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    case_id: str
    passed: bool
    failures: list[str]
    observed_source_order: list[str]
    expected_source_order: list[str]
    observed_hits: list[dict[str, object]]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "failures": list(self.failures),
            "observed_source_order": list(self.observed_source_order),
            "expected_source_order": list(self.expected_source_order),
            "observed_hits": [dict(hit) for hit in self.observed_hits],
        }


@dataclass(frozen=True, slots=True)
class EvalSuiteResult:
    passed: bool
    cases: list[EvalCaseResult]
    schema_version: str = EVAL_SUITE_SCHEMA_VERSION

    @property
    def case_count(self) -> int:
        return len(self.cases)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "passed": self.passed,
            "case_count": self.case_count,
            "cases": [case.to_json_dict() for case in self.cases],
        }


def load_eval_cases_json(path: str | Path) -> list[EvalCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != EVAL_CASES_SCHEMA_VERSION:
        raise ValueError("invalid eval cases schema_version")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("eval cases must contain a cases list")
    return [_case_from_json_dict(item) for item in cases]


def run_eval_suite(
    *,
    index_path: str | Path,
    graph_path: str | Path,
    cases_path: str | Path,
    timestamp: str,
    top_k: int = 8,
) -> EvalSuiteResult:
    cases = load_eval_cases_json(cases_path)
    results = [
        _run_case(
            case,
            index_path=index_path,
            graph_path=graph_path,
            timestamp=timestamp,
            top_k=top_k,
        )
        for case in cases
    ]
    return EvalSuiteResult(passed=all(case.passed for case in results), cases=results)


def evaluate_case_packet(case: EvalCase, packet: Mapping[str, object]) -> EvalCaseResult:
    observed_hits = summarize_hits_from_packet(packet)
    unique_hits = _unique_hits_by_source(observed_hits)
    baseline = evaluate_baseline(hits=unique_hits, expected_source_order=case.expected_source_order)
    failures = list(baseline.failures)
    for source_id, max_rank in case.max_rank_by_source.items():
        try:
            observed_rank = baseline.observed_source_order.index(source_id) + 1
        except ValueError:
            continue
        if observed_rank > max_rank:
            failures.append("rank_threshold_miss")
    for hit in observed_hits:
        if hit.get("claims_user_approval") and hit.get("authority") != "user_direct":
            failures.append("approval_promotion")
    failures = sorted(set(failures))
    return EvalCaseResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
        observed_source_order=baseline.observed_source_order,
        expected_source_order=baseline.expected_source_order,
        observed_hits=observed_hits,
    )


def summarize_hits_from_packet(packet: Mapping[str, object]) -> list[dict[str, object]]:
    items = packet.get("items", [])
    if not isinstance(items, list):
        return []
    return [_hit_from_item(item) for item in items]


def _case_from_json_dict(data: Mapping[str, object]) -> EvalCase:
    expected = data.get("expected_source_order")
    if not isinstance(expected, list) or not expected:
        raise ValueError("eval case requires non-empty expected_source_order")
    rank_thresholds = data.get("max_rank_by_source", {})
    if not isinstance(rank_thresholds, dict):
        raise ValueError("max_rank_by_source must be an object")
    return EvalCase(
        case_id=str(data["case_id"]),
        query=str(data["query"]),
        expected_source_order=[str(item) for item in expected],
        max_rank_by_source={str(key): int(value) for key, value in rank_thresholds.items()},
    )


def _run_case(
    case: EvalCase,
    *,
    index_path: str | Path,
    graph_path: str | Path,
    timestamp: str,
    top_k: int,
) -> EvalCaseResult:
    packet = query_artifacts_json(
        index_path=index_path,
        graph_path=graph_path,
        query=case.query,
        timestamp=timestamp,
        top_k=top_k,
    )
    return evaluate_case_packet(case, packet)


def _unique_hits_by_source(hits: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for hit in hits:
        source_id = str(hit.get("source_id", ""))
        if source_id and source_id not in seen:
            seen.add(source_id)
            unique.append(dict(hit))
    return unique


def _hit_from_item(item: object) -> dict[str, object]:
    if not isinstance(item, dict):
        return {"source_id": "", "stale_flags": []}
    evidence = item.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    return {
        "source_id": _source_key(evidence),
        "chunk_id": _clean_str(evidence.get("chunk_id", "")),
        "content_hash": _clean_str(evidence.get("content_hash", "")),
        "source_content_hash": _clean_str(evidence.get("source_content_hash", "")),
        "authority": _clean_str(item.get("authority", "")),
        "evidence_authority": _clean_str(evidence.get("authority", "")),
        "stale_flags": list(evidence.get("stale_flags", []) or []),
        "quarantine_flags": list(evidence.get("quarantine_flags", []) or []),
        "claims_user_approval": bool(item.get("claims_user_approval", False)),
    }


def _source_key(evidence: Mapping[str, object]) -> str:
    source_id = _clean_str(evidence.get("source_id", ""))
    if source_id:
        return source_id
    return _clean_str(evidence.get("source_uri", ""))


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value)
