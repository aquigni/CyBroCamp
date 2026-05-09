from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_CANONICAL_VAULT_ROOT = Path("/opt/obs/vault")
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|authorization|bearer|password|token|secret)\s*[:=]\s*[^\s,;]+")
_ABS_PATH_RE = re.compile(r"/(?:home|Users|opt|etc|var)/[^\s,'\")]+")


def build_dream_context_bundle(
    *,
    night: str,
    timestamp: str,
    auto_promotion_audit_path: str | Path | None = None,
    mempalace_deltas_path: str | Path | None = None,
) -> dict[str, Any]:
    return _scrub(
        {
            "schema_version": "cybrocamp.dream_context_bundle.v1",
            "night": night,
            "timestamp": timestamp,
            "output_policy": _output_policy(),
            "authority_policy": _authority_policy(),
            "auto_promotion": _parse_auto_promotion_audit(auto_promotion_audit_path),
            "mempalace_deltas": _load_safe_json(mempalace_deltas_path, default={"drawers": []}),
        }
    )


def build_event_ledger(
    *,
    timestamp: str,
    dream_archive_paths: Sequence[str | Path] = (),
    auto_promotion_audit_path: str | Path | None = None,
    cron_jobs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for path in dream_archive_paths:
        p = Path(path)
        if not p.exists() or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        events.append(
            _event(
                event_type="dream_archive",
                source_ref=str(p),
                summary=_first_heading_or_name(text, p.stem),
                timestamp=timestamp,
                metadata={
                    "sha256": _sha256_text(text),
                    "review_verdict": _regex_value(text, r"review_verdict:\s*([^\n]+)") or _regex_value(text, r"verdict:\s*([^\n]+)"),
                },
            )
        )
    audit = _parse_auto_promotion_audit(auto_promotion_audit_path)
    if audit.get("latest_entry"):
        latest = audit["latest_entry"]
        events.append(
            _event(
                event_type="auto_promotion_audit",
                source_ref=str(auto_promotion_audit_path),
                summary=latest.get("summary", "auto-promotion audit entry"),
                timestamp=str(latest.get("timestamp") or timestamp),
                metadata=latest,
            )
        )
    for job in cron_jobs:
        name = str(job.get("name") or "")
        job_id = str(job.get("job_id") or job.get("id") or "")
        if not name and not job_id:
            continue
        events.append(
            _event(
                event_type="cron_job_state",
                source_ref=f"cron:{job_id or name}",
                summary=f"{name or job_id}: {job.get('last_status') or job.get('state') or 'unknown'}",
                timestamp=timestamp,
                metadata={
                    "job_id": job_id,
                    "name": name,
                    "last_status": job.get("last_status"),
                    "state": job.get("state"),
                    "schedule": job.get("schedule"),
                },
            )
        )
    return _scrub(
        {
            "schema_version": "cybrocamp.cortex_event_ledger.v1",
            "timestamp": timestamp,
            "output_policy": _output_policy(),
            "authority_policy": _authority_policy(),
            "events": events,
        }
    )


def build_query_router_response(
    *,
    query: str,
    timestamp: str,
    local_recall_response: Mapping[str, Any] | None = None,
    event_ledger: Mapping[str, Any] | None = None,
    dream_context_bundle: Mapping[str, Any] | None = None,
    max_items: int = 12,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    routes: list[str] = []
    if local_recall_response:
        routes.append("local_recall")
        packet = _nested_get(local_recall_response, ["tool_response", "recall_packet"], {})
        for item in packet.get("items", []) if isinstance(packet, Mapping) else []:
            evidence = item.get("evidence", {}) if isinstance(item, Mapping) else {}
            items.append(
                {
                    "source": "local_recall",
                    "summary": evidence.get("source_uri") or evidence.get("source_id") or "local recall hit",
                    "score": item.get("score") if isinstance(item, Mapping) else None,
                    "evidence": evidence,
                    "authority_class": "derived_summary",
                    "grants_permission": False,
                }
            )
    if event_ledger:
        routes.append("event_ledger")
        for event in event_ledger.get("events", []) if isinstance(event_ledger, Mapping) else []:
            items.append(
                {
                    "source": "event_ledger",
                    "summary": event.get("summary", "cortex event") if isinstance(event, Mapping) else "cortex event",
                    "evidence": {"event_id": event.get("event_id"), "source_ref": event.get("source_ref")} if isinstance(event, Mapping) else {},
                    "authority_class": "derived_summary",
                    "grants_permission": False,
                }
            )
    if dream_context_bundle:
        routes.append("dream_context")
        latest = _nested_get(dream_context_bundle, ["auto_promotion", "latest_entry"], {})
        if latest:
            items.append(
                {
                    "source": "dream_context",
                    "summary": f"latest auto-promotion audit: {latest.get('timestamp', 'unknown')}",
                    "evidence": latest,
                    "authority_class": "derived_summary",
                    "grants_permission": False,
                }
            )
    return _scrub(
        {
            "schema_version": "cybrocamp.query_router_response.v1",
            "query": query,
            "timestamp": timestamp,
            "routes_used": routes,
            "items": items[:max_items],
            "policy_warnings": [],
            "output_policy": _output_policy(),
            "authority_policy": {**_authority_policy(), "association_grants_facthood": False},
        }
    )


def build_nightly_cortex_eval(
    *,
    night: str,
    timestamp: str,
    router_responses: Sequence[Mapping[str, Any]],
    dream_archive_index_path: str | Path | None = None,
    expected_archive_entries: Sequence[str] = (),
) -> dict[str, Any]:
    failures: list[str] = []
    case_results: list[dict[str, Any]] = []
    for response in router_responses:
        items = response.get("items", []) if isinstance(response, Mapping) else []
        ok = bool(items)
        if not ok and "no_router_hits" not in failures:
            failures.append("no_router_hits")
        warnings = response.get("policy_warnings", []) if isinstance(response, Mapping) else []
        case_results.append({"query": response.get("query"), "hit_count": len(items), "passed": ok and not warnings, "policy_warnings": warnings})
    archive_text = ""
    if dream_archive_index_path is not None and Path(dream_archive_index_path).exists():
        archive_text = Path(dream_archive_index_path).read_text(encoding="utf-8", errors="replace")
    missing = [entry for entry in expected_archive_entries if entry not in archive_text]
    if missing:
        failures.append("archive_index_missing_entries")
    return _scrub(
        {
            "schema_version": "cybrocamp.nightly_cortex_eval.v1",
            "night": night,
            "timestamp": timestamp,
            "case_count": len(router_responses),
            "passed": not failures,
            "failures": failures,
            "case_results": case_results,
            "archive_index": {"fresh": not missing, "missing_entries": missing},
            "output_policy": _output_policy(),
            "authority_policy": _authority_policy(),
        }
    )


def build_dream_archive_index(*, dream_dir: str | Path, existing_readme: str = "") -> str:
    dreams = Path(dream_dir)
    entries = []
    if dreams.exists():
        for path in sorted(dreams.glob("*.md")):
            if path.name == "README.md":
                continue
            entries.append(path.stem)
    header = "# CyBroSwarm shared dream archive\n\n"
    intro = (
        "Status: `phase2_active_bounded`\n"
        "Canonical protocol: [[../swarm-dreaming-protocol]]\n\n"
        "This directory is the human-readable shared dream archive for CyBroSwarm.\n\n"
        "## Authority rules\n\n"
        "- dream proposal ≠ command;\n"
        "- peer claim ≠ approval;\n"
        "- retrieval ≠ authority;\n"
        "- repetition ≠ facthood;\n"
        "- CyBroCamp evidence routing ≠ permission layer.\n\n"
    )
    suffix = ""
    existing_entry_lines: dict[str, str] = {}
    if existing_readme and "## Current entries" in existing_readme:
        prefix, rest = existing_readme.split("## Current entries", 1)
        marker = re.search(r"\n##\s+", rest)
        entry_block = rest[: marker.start()] if marker else rest
        for line in entry_block.splitlines():
            match = re.search(r"\[\[([^\]]+)\]\]", line)
            if match:
                existing_entry_lines[match.group(1)] = line.strip()
        if marker:
            suffix = rest[marker.start() + 1 :].rstrip() + "\n"
    elif existing_readme:
        prefix = existing_readme.rstrip() + "\n\n"
    else:
        prefix = header + intro
    if "dream proposal ≠ command" not in prefix:
        prefix = header + intro + prefix.split("# CyBroSwarm shared dream archive", 1)[-1].lstrip()
    lines = [prefix.rstrip(), "", "## Current entries", ""]
    for stem in entries:
        lines.append(existing_entry_lines.get(stem, f"- [[{stem}]]"))
    lines.append("")
    if suffix:
        lines.append(suffix)
    return "\n".join(lines)


def write_json_atomic(path: str | Path, data: Mapping[str, Any]) -> Path:
    out = Path(path).expanduser().resolve(strict=False)
    if _path_contains_canonical_vault(out):
        raise ValueError("JSON automation artifacts must not be written inside canonical vault")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=out.parent, delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out)
    return out


def write_text_atomic(path: str | Path, text: str, *, allow_canonical_vault: bool = False) -> Path:
    out = Path(path).expanduser().resolve(strict=False)
    if not allow_canonical_vault and _path_contains_canonical_vault(out):
        raise ValueError("text output must not be inside canonical vault unless explicitly allowed")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=out.parent, delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(out)
    return out


def _parse_auto_promotion_audit(path: str | Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {"available": False, "latest_entry": None, "entries_seen": 0}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    entries = []
    for match in re.finditer(r"^##\s+([^\n]+)\n(?P<body>.*?)(?=^##\s+|\Z)", text, flags=re.M | re.S):
        title = match.group(1).strip()
        body = match.group("body").strip()
        entries.append(
            {
                "timestamp": title.split(" — ", 1)[0].strip(),
                "summary": _summarize_lines(body),
                "promoted": _regex_value(body, r"promoted(?:_count)?:\s*([^\n]+)"),
                "quarantined_or_rejected": _regex_value(body, r"quarantined(?:_or_rejected|/rejected| count)?:\s*([^\n]+)"),
                "blockers": _regex_value(body, r"blockers?:\s*([^\n]+)") or _regex_value(body, r"blocker:\s*([^\n]+)"),
            }
        )
    return {"available": True, "latest_entry": entries[-1] if entries else None, "entries_seen": len(entries)}


def _load_safe_json(path: str | Path | None, *, default: Any) -> Any:
    if path is None or not Path(path).exists():
        return default
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _scrub(data)


def _event(*, event_type: str, source_ref: str, summary: str, timestamp: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    seed = f"{event_type}|{source_ref}|{timestamp}|{summary}"
    return {
        "event_id": "evt_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
        "event_type": event_type,
        "timestamp": timestamp,
        "source_ref": source_ref,
        "summary": summary,
        "metadata": dict(metadata),
        "authority_class": "derived_summary",
        "grants_facthood": False,
        "grants_permission": False,
        "grants_approval": False,
    }


def _output_policy() -> dict[str, bool]:
    return {"canonical_writes": False, "network_calls": False, "approval_state_writes": False, "service_mutations": False}


def _authority_policy() -> dict[str, bool]:
    return {
        "retrieval_grants_authority": False,
        "peer_claim_grants_approval": False,
        "dream_proposal_grants_command": False,
        "repetition_grants_facthood": False,
    }


def _nested_get(data: Mapping[str, Any], keys: Sequence[str], default: Any) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def _first_heading_or_name(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip() or fallback
    return fallback


def _regex_value(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _summarize_lines(text: str, limit: int = 240) -> str:
    compact = " ".join(line.strip(" -") for line in text.splitlines() if line.strip())
    return compact[:limit]


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(_scrub(k)): _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_scrub(v) for v in value]
    if isinstance(value, str):
        return _ABS_PATH_RE.sub("[REDACTED_PATH]", _SECRET_RE.sub("[REDACTED_SECRET]", value))
    return value


def _path_contains_canonical_vault(path: Path) -> bool:
    try:
        path.relative_to(_CANONICAL_VAULT_ROOT)
        return True
    except ValueError:
        return False
