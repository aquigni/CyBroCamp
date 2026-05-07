from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence as AbcSequence
from typing import Any, Mapping, Sequence

LIVING_SWARM_MEMORY_SCHEMA_VERSION = "cybrocamp.living_swarm_memory.v1"
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)\s*[:=]"
)
_SECRET_TERM_RE = re.compile(r"(?i)(api[_ -]?key|secret|token|bearer|password|passwd|private[_ -]?key|credential|cookie)")
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._~+@:-]+){2,}")


@dataclass(frozen=True, slots=True)
class LivingSwarmMemoryPacket:
    night: str
    phase_state: str
    archive_entry: dict[str, object]
    sister_contributions: dict[str, object]
    contradiction_graph: list[dict[str, object]]
    promotion_queue: list[dict[str, object]]
    health_metrics: dict[str, object]
    packet_hash: str
    redaction_counts: dict[str, int]
    schema_version: str = LIVING_SWARM_MEMORY_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_name": "cybrocamp-memory",
            "generator_version": "living-swarm-memory-stage1",
            "packet_hash": self.packet_hash,
            "night": self.night,
            "phase_state": self.phase_state,
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
            "archive_entry": dict(self.archive_entry),
            "sister_contributions": dict(self.sister_contributions),
            "contradiction_graph": list(self.contradiction_graph),
            "promotion_queue": list(self.promotion_queue),
            "health_metrics": dict(self.health_metrics),
            "redaction_counts": dict(self.redaction_counts),
        }


def build_living_memory_packet(
    *,
    night: str,
    phase_state: str = "phase2_active_bounded",
    jobs: Mapping[str, Any] | None = None,
    sisters: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    health_metrics: Mapping[str, Any] | None = None,
    contradiction_candidates: Sequence[Mapping[str, Any]] | None = None,
    promotion_candidates: Sequence[Mapping[str, Any]] | None = None,
) -> LivingSwarmMemoryPacket:
    redaction_counts = {"secret_terms": 0, "paths": 0}
    safe_jobs = _sanitize_value(dict(jobs or {}), redaction_counts)
    safe_sisters = _normalize_sisters(_sanitize_value(dict(sisters or {}), redaction_counts))
    safe_artifacts = _sanitize_value(dict(artifacts or {}), redaction_counts)
    safe_health = _sanitize_value(dict(health_metrics or {}), redaction_counts)

    archive_entry = {
        "night": night,
        "phase_state": phase_state,
        "jobs": safe_jobs,
        "artifacts": safe_artifacts,
        "health_metrics_mode": "diagnostic_only",
        "rollback": [
            "revert the vault/code commit that introduced the artifact",
            "mark the archive entry superseded or invalidated instead of silent rewrite",
        ],
    }
    contradiction_graph = _build_contradiction_graph(contradiction_candidates or [], redaction_counts)
    promotion_queue = _build_promotion_queue(promotion_candidates or [], redaction_counts)
    body = {
        "night": night,
        "phase_state": phase_state,
        "archive_entry": archive_entry,
        "sister_contributions": safe_sisters,
        "contradiction_graph": contradiction_graph,
        "promotion_queue": promotion_queue,
        "health_metrics": safe_health,
    }
    return LivingSwarmMemoryPacket(
        night=night,
        phase_state=phase_state,
        archive_entry=archive_entry,
        sister_contributions=safe_sisters,
        contradiction_graph=contradiction_graph,
        promotion_queue=promotion_queue,
        health_metrics=safe_health,
        packet_hash=_stable_hash(body),
        redaction_counts=redaction_counts,
    )


def write_living_memory_packet_json(path: str | Path, packet: LivingSwarmMemoryPacket) -> None:
    target = Path(path)
    _reject_canonical_vault_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(packet.to_json_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _normalize_sisters(sisters: object) -> dict[str, object]:
    if not isinstance(sisters, Mapping):
        return {}
    normalized: dict[str, object] = {}
    for name, value in sisters.items():
        if isinstance(value, Mapping):
            item = dict(value)
            item.setdefault("state", item.get("contribution_state", "unknown"))
            item.setdefault("authority_class", "a2a_peer_claim")
            if str(name) == "debi0":
                item.setdefault("role", "bounded_readonly")
            normalized[str(name)] = item
        else:
            normalized[str(name)] = {"state": str(value), "authority_class": "a2a_peer_claim"}
    return normalized


def _build_contradiction_graph(candidates: Sequence[Mapping[str, Any]], redaction_counts: dict[str, int]) -> list[dict[str, object]]:
    graph: list[dict[str, object]] = []
    for item in candidates:
        safe = _sanitize_value(dict(item), redaction_counts)
        graph.append(
            {
                "subject": safe.get("subject", "unknown") if isinstance(safe, Mapping) else "unknown",
                "claim_a": safe.get("claim_a", {}) if isinstance(safe, Mapping) else {},
                "claim_b": safe.get("claim_b", {}) if isinstance(safe, Mapping) else {},
                "status": "candidate",
                "resolution_policy": "do not promote either side without evidence/authority gate",
            }
        )
    return graph


def _build_promotion_queue(candidates: Sequence[Mapping[str, Any]], redaction_counts: dict[str, int]) -> list[dict[str, object]]:
    queue: list[dict[str, object]] = []
    for item in candidates:
        safe = _sanitize_value(dict(item), redaction_counts)
        kind = _normalize_kind(safe.get("kind", "unknown")) if isinstance(safe, Mapping) else "unknown"
        human_gated = kind in {"service_identity", "service", "identity", "permission", "approval_boundary"}
        queue.append(
            {
                "kind": kind,
                "subject": safe.get("subject", "unknown") if isinstance(safe, Mapping) else "unknown",
                "action": safe.get("action", "propose") if isinstance(safe, Mapping) else "propose",
                "gate": "human_required" if human_gated else "sister_reviewed_low_risk_proposal",
                "executable": False,
                "authority_class": "proposal_not_command",
                "review_policy": "sister co-review may recommend; execution requires the listed gate",
            }
        )
    return queue


def _sanitize_value(value: object, redaction_counts: dict[str, int]) -> object:
    if isinstance(value, str):
        return _safe_report_value(value, redaction_counts)
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_str = str(key)
            if _SECRET_TERM_RE.search(key_str):
                redaction_counts["secret_terms"] += 1
                sanitized["[REDACTED_SECRET]"] = "[REDACTED_SECRET]"
            else:
                sanitized[str(_sanitize_value(key_str, redaction_counts))] = _sanitize_value(item, redaction_counts)
        return sanitized
    if isinstance(value, AbcSequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(item, redaction_counts) for item in value]
    return value


def _normalize_kind(value: object) -> str:
    return re.sub(r"[\s-]+", "_", str(value).strip().lower())


def _safe_report_value(value: str, redaction_counts: dict[str, int]) -> str:
    if _SECRET_ASSIGNMENT_RE.search(value):
        redaction_counts["secret_terms"] += 1
        return "[REDACTED_SECRET]"
    path_redacted = _ABSOLUTE_PATH_RE.sub("[REDACTED_PATH]", value)
    if path_redacted != value:
        redaction_counts["paths"] += 1
    if _SECRET_TERM_RE.search(path_redacted):
        redaction_counts["secret_terms"] += 1
        return "[REDACTED_SECRET]"
    return path_redacted


def _stable_hash(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_canonical_vault_output(path: Path) -> None:
    resolved_vault = Path("/opt/obs/vault").resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path == resolved_vault or resolved_vault in resolved_path.parents:
        raise ValueError("CyBroCamp derived output must not be inside canonical vault")
