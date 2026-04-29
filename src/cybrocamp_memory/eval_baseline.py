from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class BaselineResult:
    passed: bool
    failures: list[str]
    observed_source_order: list[str]
    expected_source_order: list[str]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "failures": list(self.failures),
            "observed_source_order": list(self.observed_source_order),
            "expected_source_order": list(self.expected_source_order),
        }


def evaluate_baseline(
    *,
    hits: Sequence[Mapping[str, object]],
    expected_source_order: Sequence[str],
) -> BaselineResult:
    observed = [str(hit.get("source_id", "")) for hit in hits]
    expected = [str(item) for item in expected_source_order]
    failures: list[str] = []
    if any(item not in observed for item in expected):
        failures.append("missing_expected_source")
    observed_expected = [item for item in observed if item in expected]
    if observed_expected[: len(expected)] != expected:
        if "missing_expected_source" not in failures:
            failures.append("ranking_drift")
        elif observed_expected:
            failures.append("ranking_drift")
    expected_hits = [hit for hit in hits if str(hit.get("source_id", "")) in expected]
    if any(hit.get("stale_flags") for hit in expected_hits):
        failures.append("stale_expected_hit")
    return BaselineResult(
        passed=not failures,
        failures=failures,
        observed_source_order=observed,
        expected_source_order=expected,
    )
