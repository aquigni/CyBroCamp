from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

CORTEX_ROLLOUT_SCHEMA_VERSION = "cybrocamp.cortex_rollout.v1"
_SECRET_TERM_RE = re.compile(r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class CortexRollout:
    sisters: list[dict[str, object]]
    timestamp: str
    rollout_hash: str
    diagnostics: dict[str, object]
    schema_version: str = CORTEX_ROLLOUT_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_name": "cybrocamp-memory",
            "generator_version": "stage18",
            "generated_at": self.timestamp,
            "rollout_hash": self.rollout_hash,
            "mode": "three_sister_cortex_rollout_plan",
            "output_policy": {
                "canonical_writes": False,
                "network_calls": False,
                "approval_state_writes": False,
                "service_mutations": False,
                "deterministic": True,
                "sanitization_profile": "stage18-secret-and-path-redaction",
            },
            "sisters": list(self.sisters),
            "future_sister_template": _future_template(),
            "authority_policy": {
                "peer_claim_is_user_approval": False,
                "future_auto_enrollment_grants_approval": False,
                "retrieval_grants_facthood": False,
                "promotion_requires_user_direct_authority": True,
                "canonical_write_requires_explicit_h0st_execution_approval": True,
            },
            "example_query_flow": [
                "H0st asks Chthonya about CyBroCamp rollout state.",
                "Chthonya queries the local canonical derived index and returns provenance-backed RecallPacket metadata.",
                "Mac0sh receives a read-only knowledge_pull for local mirror corroboration; result authority is a2a_peer_claim.",
                "Debi0 may run bounded smoke/status checks only; result authority is a2a_peer_claim or ops_readonly.",
                "No sister can convert peer recall into user approval or canonical fact without explicit H0st execution approval.",
            ],
            "diagnostics": dict(self.diagnostics),
        }


def build_cortex_rollout(
    *,
    sisters: Sequence[Mapping[str, object]] | None = None,
    timestamp: str,
) -> CortexRollout:
    redaction_counts = {"secret_terms": 0, "paths": 0}
    raw_sisters = list(sisters) if sisters is not None else _default_sisters()
    nodes = [_node_from_mapping(item, redaction_counts) for item in raw_sisters]
    nodes = sorted(nodes, key=lambda item: str(item["sister_id"]))
    diagnostics = {
        "sister_count": len(nodes),
        "future_auto_enroll_default": "quarantined_readonly_until_explicit_approval",
        "redaction_counts": redaction_counts,
        "warnings": [],
        "errors": [],
    }
    rollout_body = {"sisters": nodes, "future_sister_template": _future_template(), "timestamp": timestamp}
    return CortexRollout(sisters=nodes, timestamp=timestamp, rollout_hash=_stable_hash(rollout_body), diagnostics=diagnostics)


def write_cortex_rollout_json(path: str | Path, rollout: CortexRollout) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(rollout.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _default_sisters() -> list[dict[str, object]]:
    return [
        {"sister_id": "chthonya", "host_label": "server canonical builder", "role": "canonical_builder"},
        {"sister_id": "mac0sh", "host_label": "mac local mirror reviewer", "role": "reviewer"},
        {"sister_id": "debi0", "host_label": "debian bounded worker", "role": "bounded_readonly"},
    ]


def _node_from_mapping(item: Mapping[str, object], redaction_counts: dict[str, int]) -> dict[str, object]:
    sister_id = _safe_report_value(str(item.get("sister_id", "unknown")), redaction_counts)
    role = _safe_report_value(str(item.get("role", "future_readonly")), redaction_counts)
    host_label = _safe_report_value(str(item.get("host_label", "unspecified")), redaction_counts)
    return {
        "sister_id": sister_id,
        "role": role,
        "host_label": host_label,
        "status": "active_rollout_member" if sister_id in {"chthonya", "mac0sh", "debi0"} else "quarantined_readonly_until_explicit_approval",
        "rights": _rights_for_role(role),
        "authority_emitted": "canonical_vault" if role == "canonical_builder" else "a2a_peer_claim",
        "approval_boundary": "cannot_grant_or_infer_h0st_approval",
    }


def _rights_for_role(role: str) -> dict[str, bool]:
    base = {
        "can_query": True,
        "can_build_local_index": False,
        "can_build_canonical_index": False,
        "can_review": False,
        "can_preview_promotions": False,
        "can_execute_promotions": False,
        "can_write_canonical_mempalace": False,
        "can_grant_h0st_approval": False,
        "can_mutate_services": False,
    }
    if role == "canonical_builder":
        base.update(can_build_local_index=True, can_build_canonical_index=True, can_review=True, can_preview_promotions=True)
    elif role == "reviewer":
        base.update(can_build_local_index=True, can_review=True, can_preview_promotions=True)
    elif role == "bounded_readonly":
        base.update(can_build_local_index=False, can_review=False)
    return base


def _future_template() -> dict[str, object]:
    return {
        "sister_id": "future-sister-*",
        "role": "future_readonly",
        "status": "quarantined_readonly_until_explicit_approval",
        "rights": _rights_for_role("future_readonly"),
        "enrollment_steps": [
            "assign stable sister_id",
            "register read-only knowledge_pull route",
            "run smoke tests without canonical writes",
            "require explicit H0st approval before any role elevation",
        ],
    }


def _stable_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_canonical_vault_output(path: Path) -> None:
    resolved_vault = Path("/opt/obs/vault").resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_vault or resolved_vault in resolved_path.parents:
        raise ValueError("CyBroCamp derived output must not be inside canonical vault")


def _safe_report_value(value: str, redaction_counts: dict[str, int] | None = None) -> str:
    result = value
    if _SECRET_TERM_RE.search(result):
        result = "[REDACTED_SECRET]"
        if redaction_counts is not None:
            redaction_counts["secret_terms"] += 1
    if _ABSOLUTE_PATH_RE.search(result):
        result = _ABSOLUTE_PATH_RE.sub("[REDACTED_PATH]", result)
        if redaction_counts is not None:
            redaction_counts["paths"] += 1
    return result
