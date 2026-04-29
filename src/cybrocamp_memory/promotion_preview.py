from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

LOCKED_PREVIEW_SCHEMA_VERSION = "cybrocamp.locked_preview.v1"
PREVIEW_LOCK_SCHEMA_VERSION = "cybrocamp.preview_lock.v1"
_PREVIEW_ACTION = "preview_canonical_write"
_SECRET_TERM_RE = re.compile(r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class LockedPreview:
    preview_ops: list[dict[str, object]]
    preview_writes: list[dict[str, object]]
    timestamp: str
    input_plan_hash: str
    lock_scope_hash: str | None
    diagnostics: dict[str, object]
    schema_version: str = LOCKED_PREVIEW_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_name": "cybrocamp-memory",
            "generator_version": "stage16",
            "generated_at": self.timestamp,
            "mode": "locked_preview_only",
            "input_plan_hash": self.input_plan_hash,
            "lock_scope_hash": self.lock_scope_hash,
            "output_policy": {
                "canonical_writes": False,
                "network_calls": False,
                "approval_state_writes": False,
                "output_outside_vault": True,
                "deterministic": True,
                "requires_second_h0st_approval_for_execution": True,
                "sanitization_profile": "stage16-secret-and-path-redaction",
            },
            "preview_ops": list(self.preview_ops),
            "preview_writes": list(self.preview_writes),
            "diagnostics": dict(self.diagnostics),
        }


def build_locked_preview(
    promotion_plan: Mapping[str, object],
    *,
    lock_scope: Mapping[str, object] | None = None,
    timestamp: str,
) -> LockedPreview:
    plan_hash = _stable_hash(promotion_plan)
    locked = _lock_scope_index(lock_scope, plan_hash)
    redaction_counts = {"secret_terms": 0, "paths": 0}
    preview_ops: list[dict[str, object]] = []
    preview_writes: list[dict[str, object]] = []
    raw_ops = promotion_plan.get("dry_run_ops", [])
    if not isinstance(raw_ops, list):
        raw_ops = []
    for index, raw_op in enumerate(raw_ops):
        if not isinstance(raw_op, Mapping):
            continue
        op, preview_write = _preview_op(raw_op, index=index, locked=locked, redaction_counts=redaction_counts)
        preview_ops.append(op)
        if preview_write is not None:
            preview_writes.append(preview_write)
    diagnostics = {
        "input_op_count": len(preview_ops),
        "locked_preview_count": len(preview_writes),
        "lock_required": lock_scope is None,
        "redaction_counts": redaction_counts,
        "warnings": [] if lock_scope else ["missing_preview_lock_zero_preview_writes"],
        "errors": [],
    }
    return LockedPreview(
        preview_ops=sorted(preview_ops, key=lambda item: str(item["op_id"])),
        preview_writes=sorted(preview_writes, key=lambda item: str(item["op_id"])),
        timestamp=timestamp,
        input_plan_hash=plan_hash,
        lock_scope_hash=_stable_hash(lock_scope) if lock_scope is not None else None,
        diagnostics=diagnostics,
    )


def write_locked_preview_json(path: str | Path, preview: LockedPreview) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(preview.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _preview_op(
    raw_op: Mapping[str, object],
    *,
    index: int,
    locked: set[str],
    redaction_counts: dict[str, int],
) -> tuple[dict[str, object], dict[str, object] | None]:
    op_id = _safe_report_value(str(raw_op.get("op_id", f"op-{index:06d}")), redaction_counts)
    candidate_id = _safe_report_value(str(raw_op.get("candidate_id", "")), redaction_counts)
    op_type = _safe_report_value(str(raw_op.get("op_type", "")), redaction_counts)
    target_kind = _safe_report_value(str(raw_op.get("target_kind", "")), redaction_counts)
    target_id = _safe_report_value(str(raw_op.get("target_id_or_hash", "")), redaction_counts)
    label = _safe_report_value(str(raw_op.get("sanitized_target_label", "")), redaction_counts)
    source_op_id = str(raw_op.get("op_id", f"op-{index:06d}"))
    block_reasons: list[str] = []
    if raw_op.get("dry_run") is not True or raw_op.get("would_write") is not False:
        block_reasons.append("source_op_not_stage15_dry_run")
    if source_op_id not in locked:
        block_reasons.append("missing_or_mismatched_preview_lock")
    preview_status = "locked_for_execution_preview" if not block_reasons else "blocked_by_preview_policy"
    preview_op = {
        "op_id": op_id,
        "candidate_id": candidate_id,
        "op_type": op_type,
        "target_kind": target_kind,
        "target_id_or_hash": target_id,
        "sanitized_target_label": label,
        "status": preview_status,
        "block_reasons": sorted(set(block_reasons)),
        "canonical_write_enabled": False,
        "execution_requires_second_approval": True,
    }
    if block_reasons:
        return preview_op, None
    receipt_draft = {
        "receipt_schema_version": "cybrocamp.promotion_receipt.v1",
        "op_id": op_id,
        "candidate_id": candidate_id,
        "target_kind": target_kind,
        "target_id_or_hash": target_id,
        "execution_allowed": False,
        "approval_layer": "preview_lock_only",
        "requires_execution_approval_schema": "cybrocamp.execution_approval.v1",
    }
    preview_write = {
        "op_id": op_id,
        "candidate_id": candidate_id,
        "op_type": op_type,
        "target_kind": target_kind,
        "target_id_or_hash": target_id,
        "sanitized_target_label": label,
        "would_write": False,
        "canonical_write_enabled": False,
        "network_call_enabled": False,
        "receipt_draft": receipt_draft,
    }
    return preview_op, preview_write


def _lock_scope_index(scope: Mapping[str, object] | None, plan_hash: str) -> set[str]:
    if scope is None:
        return set()
    if scope.get("schema_version") != PREVIEW_LOCK_SCHEMA_VERSION:
        return set()
    if scope.get("approved_by") != "H0st" or scope.get("plan_hash") != plan_hash:
        return set()
    locked: set[str] = set()
    for entry in scope.get("locked_ops", []) or []:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("approved_by", scope.get("approved_by")) != "H0st":
            continue
        if entry.get("action") == _PREVIEW_ACTION and entry.get("op_id"):
            locked.add(str(entry["op_id"]))
    return locked


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
