from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Any

DREAM_REVIEW_SCHEMA_VERSION = "cybrocamp.dream_review.v1"
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)\s*[:=]\s*[^\s,;}]+"
)
_SECRET_TERM_RE = re.compile(r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class DreamReview:
    verdict: str
    timestamp: str
    diagnostics: dict[str, object]
    review_hash: str
    schema_version: str = DREAM_REVIEW_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_name": "cybrocamp-memory",
            "generator_version": "dream-review-stage1",
            "generated_at": self.timestamp,
            "review_hash": self.review_hash,
            "verdict": self.verdict,
            "output_policy": {
                "canonical_writes": False,
                "network_calls": False,
                "approval_state_writes": False,
                "service_mutations": False,
                "diagnostic_only": True,
            },
            "authority_policy": {
                "retrieval_grants_authority": False,
                "peer_claim_grants_approval": False,
                "dream_proposal_grants_command": False,
                "repetition_grants_facthood": False,
                "cybrocamp_is_permission_layer": False,
                "service_identity_promotion_human_gated": True,
            },
            "diagnostics": dict(self.diagnostics),
        }


def build_dream_review(packet: Mapping[str, Any], *, timestamp: str) -> DreamReview:
    """Build a non-writing review artifact for a CyBroSwarm dream packet.

    The review is an evidence-safety diagnostic only. It never performs or
    authorizes canonical writes, service changes, or authority promotion.
    """
    redaction_counts = {"secret_terms": 0, "paths": 0}
    safe_packet = _sanitize_value(packet, redaction_counts)
    warnings: list[str] = []
    errors: list[str] = []

    authority_policy = safe_packet.get("authority_policy") if isinstance(safe_packet, dict) else None
    if not isinstance(authority_policy, Mapping):
        errors.append("missing_authority_policy")
    else:
        if authority_policy.get("retrieval_is_authority") is not False:
            errors.append("retrieval_authority_promotion")
        if authority_policy.get("peer_claim_is_approval") is not False:
            errors.append("peer_claim_approval_promotion")
        if authority_policy.get("dream_proposal_is_command") is not False:
            errors.append("dream_command_promotion")
        if authority_policy.get("repetition_is_facthood") is not False:
            errors.append("repetition_facthood_promotion")

    sisters = safe_packet.get("sisters", {}) if isinstance(safe_packet, dict) else {}
    if isinstance(sisters, Mapping):
        debi0 = sisters.get("debi0")
        if isinstance(debi0, Mapping):
            role = str(debi0.get("role", "bounded_readonly"))
            if role not in {"bounded_readonly", "receipt", "status", "smoke"}:
                warnings.append("debi0_role_expansion_blocked")

    promotions = safe_packet.get("promotion_candidates", []) if isinstance(safe_packet, dict) else []
    if isinstance(promotions, list):
        for item in promotions:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("kind", "")) in {"service_identity", "service", "identity", "permission"} and item.get("human_approved") is not True:
                warnings.append("service_identity_promotion_requires_human_approval")
                break

    metrics = safe_packet.get("metrics", {}) if isinstance(safe_packet, dict) else {}
    diagnostics = {
        "metrics_mode": "diagnostic_only",
        "metrics": metrics if isinstance(metrics, Mapping) else {},
        "sister_states": _sister_states(sisters),
        "warnings": sorted(set(warnings)),
        "errors": sorted(set(errors)),
        "redaction_counts": redaction_counts,
    }
    verdict = "block" if errors else "revise" if warnings else "pass"
    body = {"timestamp": timestamp, "verdict": verdict, "diagnostics": diagnostics}
    return DreamReview(verdict=verdict, timestamp=timestamp, diagnostics=diagnostics, review_hash=_stable_hash(body))


def write_dream_review_json(path: str | Path, review: DreamReview) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(review.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _sister_states(sisters: object) -> dict[str, object]:
    if not isinstance(sisters, Mapping):
        return {}
    states: dict[str, object] = {}
    for name, data in sisters.items():
        if isinstance(data, Mapping):
            states[str(name)] = {
                "contribution_state": data.get("contribution_state", "unknown"),
                "authority_class": data.get("authority_class", "a2a_peer_claim"),
            }
    return states


def _sanitize_value(value: object, redaction_counts: dict[str, int]) -> object:
    if isinstance(value, str):
        return _safe_report_value(value, redaction_counts)
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for k, v in value.items():
            key = str(k)
            if _SECRET_TERM_RE.search(key):
                redaction_counts["secret_terms"] += 1
                sanitized["[REDACTED_SECRET]"] = "[REDACTED_SECRET]"
            else:
                sanitized[str(_sanitize_value(key, redaction_counts))] = _sanitize_value(v, redaction_counts)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(v, redaction_counts) for v in value]
    return value


def _safe_report_value(value: str, redaction_counts: dict[str, int]) -> str:
    if _SECRET_ASSIGNMENT_RE.search(value):
        redaction_counts["secret_terms"] += 1
        return "[REDACTED_SECRET]"
    new_result = _ABSOLUTE_PATH_RE.sub("[REDACTED_PATH]", value)
    if new_result != value:
        redaction_counts["paths"] += 1
    if _SECRET_TERM_RE.search(new_result):
        redaction_counts["secret_terms"] += 1
        return "[REDACTED_SECRET]"
    return new_result


def _stable_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_canonical_vault_output(path: Path) -> None:
    resolved_vault = Path("/opt/obs/vault").resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_vault or resolved_vault in resolved_path.parents:
        raise ValueError("CyBroCamp derived output must not be inside canonical vault")
