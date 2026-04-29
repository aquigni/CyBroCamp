from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

EXECUTION_RECEIPT_SCHEMA_VERSION = "cybrocamp.execution_receipt.v1"
EXECUTION_APPROVAL_SCHEMA_VERSION = "cybrocamp.execution_approval.v1"
_EXECUTION_ACTION = "execute_mempalace_kg_promotion"
_SECRET_TERM_RE = re.compile(r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    reviewed_ops: list[dict[str, object]]
    executed_ops: list[dict[str, object]]
    timestamp: str
    input_preview_hash: str
    execution_approval_hash: str | None
    diagnostics: dict[str, object]
    schema_version: str = EXECUTION_RECEIPT_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_name": "cybrocamp-memory",
            "generator_version": "stage17",
            "generated_at": self.timestamp,
            "mode": "controlled_execution",
            "input_preview_hash": self.input_preview_hash,
            "execution_approval_hash": self.execution_approval_hash,
            "output_policy": {
                "canonical_writes": False,
                "network_calls": False,
                "approval_state_writes": False,
                "requires_second_h0st_approval": True,
                "local_receipt_only": True,
                "deterministic": True,
                "sanitization_profile": "stage17-secret-and-path-redaction",
            },
            "reviewed_ops": list(self.reviewed_ops),
            "executed_ops": list(self.executed_ops),
            "diagnostics": dict(self.diagnostics),
        }


def build_execution_receipt(
    locked_preview: Mapping[str, object],
    *,
    execution_approval: Mapping[str, object] | None = None,
    timestamp: str,
) -> ExecutionReceipt:
    preview_hash = _stable_hash(locked_preview)
    approved = _approval_index(execution_approval, preview_hash)
    redaction_counts = {"secret_terms": 0, "paths": 0}
    reviewed_ops: list[dict[str, object]] = []
    executed_ops: list[dict[str, object]] = []
    raw_ops = locked_preview.get("preview_writes", [])
    if not isinstance(raw_ops, list):
        raw_ops = []
    for index, raw_op in enumerate(raw_ops):
        if not isinstance(raw_op, Mapping):
            continue
        reviewed, executed = _review_and_execute(raw_op, index=index, approved=approved, redaction_counts=redaction_counts, timestamp=timestamp)
        reviewed_ops.append(reviewed)
        if executed is not None:
            executed_ops.append(executed)
    diagnostics = {
        "reviewed_count": len(reviewed_ops),
        "executed_count": len(executed_ops),
        "second_approval_required": execution_approval is None,
        "redaction_counts": redaction_counts,
        "warnings": [] if execution_approval else ["missing_execution_approval_zero_execution"],
        "errors": [],
    }
    return ExecutionReceipt(
        reviewed_ops=sorted(reviewed_ops, key=lambda item: str(item["op_id"])),
        executed_ops=sorted(executed_ops, key=lambda item: str(item["op_id"])),
        timestamp=timestamp,
        input_preview_hash=preview_hash,
        execution_approval_hash=_stable_hash(execution_approval) if execution_approval is not None else None,
        diagnostics=diagnostics,
    )


def write_execution_receipt_json(path: str | Path, receipt: ExecutionReceipt) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(receipt.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _review_and_execute(
    raw_op: Mapping[str, object],
    *,
    index: int,
    approved: set[str],
    redaction_counts: dict[str, int],
    timestamp: str,
) -> tuple[dict[str, object], dict[str, object] | None]:
    source_op_id = str(raw_op.get("op_id", f"op-{index:06d}"))
    op_id = _safe_report_value(source_op_id, redaction_counts)
    candidate_id = _safe_report_value(str(raw_op.get("candidate_id", "")), redaction_counts)
    target_kind = _safe_report_value(str(raw_op.get("target_kind", "")), redaction_counts)
    target_id = _safe_report_value(str(raw_op.get("target_id_or_hash", "")), redaction_counts)
    label = _safe_report_value(str(raw_op.get("sanitized_target_label", "")), redaction_counts)
    block_reasons: list[str] = []
    if raw_op.get("would_write") is not False or raw_op.get("canonical_write_enabled") is not False:
        block_reasons.append("preview_not_non_writing")
    if source_op_id not in approved:
        block_reasons.append("missing_or_mismatched_execution_approval")
    reviewed = {
        "op_id": op_id,
        "candidate_id": candidate_id,
        "target_kind": target_kind,
        "target_id_or_hash": target_id,
        "sanitized_target_label": label,
        "status": "executed_to_local_receipt" if not block_reasons else "blocked_by_execution_policy",
        "block_reasons": sorted(set(block_reasons)),
        "network_call_enabled": False,
        "canonical_network_write_enabled": False,
    }
    if block_reasons:
        return reviewed, None
    executed = {
        "op_id": op_id,
        "candidate_id": candidate_id,
        "target_kind": target_kind,
        "target_id_or_hash": target_id,
        "sanitized_target_label": label,
        "sink": "local_receipt_only",
        "canonical_network_write_performed": False,
        "executed_at": timestamp,
        "receipt_hash": _stable_hash({"op_id": op_id, "candidate_id": candidate_id, "target": target_id, "timestamp": timestamp}),
        "rollback_hint": "invalidate_or_remove_receipt_entry_before_any_future_canonical_writer",
    }
    return reviewed, executed


def _approval_index(scope: Mapping[str, object] | None, preview_hash: str) -> set[str]:
    if scope is None:
        return set()
    if scope.get("schema_version") != EXECUTION_APPROVAL_SCHEMA_VERSION:
        return set()
    if scope.get("approved_by") != "H0st" or scope.get("preview_hash") != preview_hash:
        return set()
    approved: set[str] = set()
    for entry in scope.get("approved_ops", []) or []:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("approved_by", scope.get("approved_by")) != "H0st":
            continue
        if entry.get("action") == _EXECUTION_ACTION and entry.get("op_id"):
            approved.add(str(entry["op_id"]))
    return approved


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
