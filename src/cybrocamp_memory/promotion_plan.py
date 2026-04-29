from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

PROMOTION_PLAN_SCHEMA_VERSION = "cybrocamp.promotion_plan.v1"
APPROVAL_SCOPE_SCHEMA_VERSION = "cybrocamp.approval_scope.v1"
_ALLOWED_ACTION = "promote_to_mempalace_kg"
_SECRET_TERM_RE = re.compile(r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class PromotionPlan:
    candidates: list[dict[str, object]]
    dry_run_ops: list[dict[str, object]]
    timestamp: str
    input_audit_hash: str
    approval_scope_hash: str | None
    diagnostics: dict[str, object]
    schema_version: str = PROMOTION_PLAN_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_name": "cybrocamp-memory",
            "generator_version": "stage15",
            "generated_at": self.timestamp,
            "mode": "dry_run",
            "input_audit_hash": self.input_audit_hash,
            "approval_scope_hash": self.approval_scope_hash,
            "output_policy": {
                "canonical_writes": False,
                "network_calls": False,
                "output_outside_vault": True,
                "deterministic": True,
                "requires_h0st_approval_for_ops": True,
                "sanitization_profile": "stage15-secret-and-path-redaction",
            },
            "candidates": list(self.candidates),
            "dry_run_ops": list(self.dry_run_ops),
            "diagnostics": dict(self.diagnostics),
        }


def build_promotion_plan(
    audit_report: Mapping[str, object],
    *,
    approval_scope: Mapping[str, object] | None = None,
    timestamp: str,
) -> PromotionPlan:
    approved = _approved_scope_index(approval_scope)
    candidates: list[dict[str, object]] = []
    ops: list[dict[str, object]] = []
    redaction_counts = {"secret_terms": 0, "paths": 0}

    raw_items = audit_report.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []

    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping):
            continue
        candidate, op = _candidate_and_op(item, index=index, approved=approved, redaction_counts=redaction_counts)
        candidates.append(candidate)
        if op is not None:
            ops.append(op)

    diagnostics = {
        "candidate_count": len(candidates),
        "approved_ops_count": len(ops),
        "blocked_items_count": sum(1 for item in candidates if item["status"] == "blocked_by_audit"),
        "rejected_items_count": sum(1 for item in candidates if item["status"] != "approved_for_dry_run"),
        "redaction_counts": redaction_counts,
        "warnings": [] if approval_scope else ["missing_approval_scope_zero_ops"],
        "errors": [],
    }
    return PromotionPlan(
        candidates=sorted(candidates, key=lambda item: str(item["candidate_id"])),
        dry_run_ops=sorted(ops, key=lambda item: str(item["op_id"])),
        timestamp=timestamp,
        input_audit_hash=_stable_hash(audit_report),
        approval_scope_hash=_stable_hash(approval_scope) if approval_scope is not None else None,
        diagnostics=diagnostics,
    )


def write_promotion_plan_json(path: str | Path, plan: PromotionPlan) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(plan.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _candidate_and_op(
    item: Mapping[str, object],
    *,
    index: int,
    approved: set[tuple[str, str]],
    redaction_counts: dict[str, int],
) -> tuple[dict[str, object], dict[str, object] | None]:
    candidate_id = _candidate_id(item)
    decision = str(item.get("decision", ""))
    subject = _safe_report_value(str(item.get("subject", "")), redaction_counts)
    predicate = _safe_report_value(str(item.get("predicate", "")), redaction_counts)
    obj = _safe_report_value(str(item.get("object", "")), redaction_counts)
    reasons = [_safe_report_value(str(reason), redaction_counts) for reason in item.get("reasons", []) or []]
    authority_chain = item.get("authority_chain", {}) if isinstance(item.get("authority_chain", {}), Mapping) else {}
    source_authority = _safe_report_value(str(authority_chain.get("candidate_authority", "unknown")), redaction_counts)
    evidence_authority = _safe_report_value(str(authority_chain.get("evidence_authority", "unknown")), redaction_counts)
    approved_for_candidate = (candidate_id, _ALLOWED_ACTION) in approved

    block_reasons: list[str] = []
    has_user_direct_authority = source_authority == "user_direct" and evidence_authority == "user_direct"
    if decision != "promotable_candidate":
        block_reasons.append("audit_decision_not_promotable")
        block_reasons.extend(reasons)
        status = "blocked_by_audit"
    elif not has_user_direct_authority:
        block_reasons.append("non_user_direct_authority_not_promotable")
        status = "blocked_by_audit"
    elif not approved_for_candidate:
        block_reasons.append("missing_exact_h0st_approval_scope")
        status = "requires_approval"
    else:
        status = "approved_for_dry_run"

    candidate = {
        "candidate_id": candidate_id,
        "audit_item_id": f"audit-item-{index:06d}",
        "source_kind": "promotion_audit_item",
        "source_authority": source_authority,
        "evidence_authority": evidence_authority,
        "sanitized_title": " ".join(part for part in [subject, predicate, obj] if part),
        "sanitized_summary": f"Would consider promoting {subject} {predicate} {obj}".strip(),
        "status": status,
        "block_reasons": sorted(set(block_reasons)),
        "approval_required": True,
        "approval_evidence": {
            "approved": approved_for_candidate and status == "approved_for_dry_run",
            "approved_by": "H0st" if approved_for_candidate and status == "approved_for_dry_run" else None,
            "approved_action": _ALLOWED_ACTION if approved_for_candidate and status == "approved_for_dry_run" else None,
            "approved_candidate_id": candidate_id if approved_for_candidate and status == "approved_for_dry_run" else None,
            "approval_match_reason": "exact_candidate_and_action_match" if approved_for_candidate else "no_exact_match",
        },
    }
    if status != "approved_for_dry_run":
        return candidate, None

    evidence = item.get("evidence_bundle", {}) if isinstance(item.get("evidence_bundle", {}), Mapping) else {}
    target_id = _safe_report_value(str(evidence.get("source_id", candidate_id)), redaction_counts)
    op = {
        "op_id": "op-" + candidate_id.removeprefix("cand-"),
        "candidate_id": candidate_id,
        "op_type": _ALLOWED_ACTION,
        "dry_run": True,
        "target_kind": "mempalace_kg_candidate",
        "target_id_or_hash": target_id,
        "sanitized_target_label": candidate["sanitized_title"],
        "preconditions": [
            "explicit_h0st_approval_scope_present",
            "source_audit_decision_promotable_candidate",
            "user_direct_candidate_and_evidence_authority",
            "dry_run_only_no_canonical_write",
        ],
        "would_write": False,
        "blocked": False,
        "block_reasons": [],
    }
    return candidate, op


def _approved_scope_index(scope: Mapping[str, object] | None) -> set[tuple[str, str]]:
    if scope is None:
        return set()
    if scope.get("schema_version") != APPROVAL_SCOPE_SCHEMA_VERSION:
        return set()
    if scope.get("approved_by") != "H0st":
        return set()
    approved: set[tuple[str, str]] = set()
    for entry in scope.get("approved_candidates", []) or []:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("approved_by", scope.get("approved_by")) != "H0st":
            continue
        candidate_id = str(entry.get("candidate_id", ""))
        action = str(entry.get("action", ""))
        if candidate_id and action == _ALLOWED_ACTION:
            approved.add((candidate_id, action))
    return approved


def _candidate_id(item: Mapping[str, object]) -> str:
    identity = {
        "subject": item.get("subject", ""),
        "predicate": item.get("predicate", ""),
        "object": item.get("object", ""),
        "evidence_bundle": {
            key: (item.get("evidence_bundle", {}) or {}).get(key, "")
            for key in ["source_id", "chunk_id", "content_hash", "source_content_hash"]
            if isinstance(item.get("evidence_bundle", {}), Mapping)
        },
    }
    return "cand-" + _stable_hash(identity).removeprefix("sha256:")[:24]


def _stable_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_canonical_vault_output(path: Path) -> None:
    resolved_vault = Path("/opt/obs/vault").resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_vault or resolved_vault in resolved_path.parents:
        raise ValueError("promotion plan output must not be inside canonical vault")


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
