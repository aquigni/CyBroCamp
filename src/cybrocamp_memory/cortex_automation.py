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


_DEFAULT_CORTEX_PROBES: tuple[tuple[str, str], ...] = (
    ("memory", "CyBroCamp Hindsight auto-promotion dreams cortex event ledger"),
    ("memory", "L1 L2 L3 memory stale contradiction promotion authority"),
    ("memory", "MemPalace tunnels KG non obvious cross project association"),
    ("memory", "Hindsight advisory recall not authorization chunks fail closed"),
    ("sisters", "Mac0sh contribution timeout late result sister review low risk hygiene"),
    ("sisters", "Debi0 deterministic receipt bounded status not reasoning capability"),
    ("sisters", "A2A sync directive vault commit mirror acknowledgement"),
    ("sisters", "future sister quarantined readonly contract descriptor"),
    ("public", "CyBroSwarm public channel morning pulse ordinary Telegram style"),
    ("public", "sensor triage public chat untrusted candidate escalation"),
    ("public", "public posting authority H0st gated ordinary channel message"),
    ("ops", "Hermes gateway OpenRouter auxiliary compression title generation"),
    ("ops", "server health memory pressure Hindsight cgroup OOM repair"),
    ("ops", "zrok private CyBroCamp cortex API bearer token registry"),
    ("ops", "Hermes live checkout dirty files cron scheduler tests"),
    ("research", "frontier research self evolving agents memory safety abstention"),
    ("research", "AgentGuard runtime verification swarm self improvement"),
    ("research", "autogenesis resource registry SEPL learnability masks"),
    ("cybrolog", "CyBroLog CL2 v2.2 compression never grants permission"),
    ("cybrolog", "CybriLog A2A dialect evidence authority proof obligation"),
    ("cybrolog", "dream proposal command peer claim approval retrieval authority"),
    ("cybrocamp", "local associative sidecar search terms term graph fact candidates"),
    ("cybrocamp", "promotion audit plan preview execute dry run approval scope"),
    ("cybrocamp", "cortex rebuild API local loopback artifact manifest"),
    ("identity", "Chthonya Mac0sh Debi0 roles authority boundaries"),
    ("survival", "CyBroSwarm survival economics Telegram research paid articles"),
)


def build_cortex_probe_set(*, timestamp: str, limit: int = 32) -> dict[str, Any]:
    capped = max(1, min(limit, 50))
    cases = [
        {
            "case_id": "probe_" + hashlib.sha256(f"{domain}|{query}".encode("utf-8")).hexdigest()[:12],
            "domain": domain,
            "query": query,
            "authority_class": "derived_eval_probe",
            "grants_permission": False,
            "grants_facthood": False,
            "expected_min_hits": 1,
        }
        for domain, query in _DEFAULT_CORTEX_PROBES[:capped]
    ]
    return _scrub(
        {
            "schema_version": "cybrocamp.cortex_probe_set.v1",
            "timestamp": timestamp,
            "case_count": len(cases),
            "cases": cases,
            "output_policy": _output_policy(),
            "authority_policy": {**_authority_policy(), "association_grants_facthood": False},
        }
    )


def build_stale_contradiction_queue(
    *,
    timestamp: str,
    event_ledger: Mapping[str, Any] | None = None,
    dream_context_bundle: Mapping[str, Any] | None = None,
    router_responses: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    events = event_ledger.get("events", []) if isinstance(event_ledger, Mapping) else []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, Mapping):
            continue
        summary = str(event.get("summary") or "")
        if re.search(r"(?i)(timeout|no visible result|no_result|late_result|blocked|failed)", summary):
            items.append(_queue_item("sister_timeout_or_no_result", summary, event.get("source_ref"), timestamp))
        if re.search(r"(?i)(contradiction|stale|duplicate|diverg)", summary):
            items.append(_queue_item("stale_or_contradiction_candidate", summary, event.get("source_ref"), timestamp))
    latest = _nested_get(dream_context_bundle or {}, ["auto_promotion", "latest_entry"], {})
    if isinstance(latest, Mapping):
        blockers = str(latest.get("blockers") or "")
        if blockers and blockers.lower() not in {"none", "нет", "no"}:
            items.append(_queue_item("auto_promotion_blocker", blockers, "auto_promotion", timestamp))
        rejected = _parse_intish(latest.get("quarantined_or_rejected"))
        if rejected >= 25:
            items.append(_queue_item("high_quarantine_or_rejection_count", f"quarantined_or_rejected={rejected}", "auto_promotion", timestamp))
    for response in router_responses:
        items_list = response.get("items", []) if isinstance(response, Mapping) else []
        warnings = response.get("policy_warnings", []) if isinstance(response, Mapping) else []
        query = response.get("query") if isinstance(response, Mapping) else None
        if not items_list:
            items.append(_queue_item("empty_retrieval_probe", f"no hits for query: {query}", "query_router", timestamp))
        for warning in warnings if isinstance(warnings, list) else []:
            items.append(_queue_item("policy_warning", str(warning), "query_router", timestamp))
    return _scrub(
        {
            "schema_version": "cybrocamp.stale_contradiction_queue.v1",
            "timestamp": timestamp,
            "items": items,
            "item_count": len(items),
            "output_policy": _output_policy(),
            "authority_policy": {**_authority_policy(), "association_grants_facthood": False},
        }
    )


def build_incremental_cortex_pulse(
    *,
    timestamp: str,
    vault_epoch: str | None = None,
    previous_state: Mapping[str, Any] | None = None,
    event_ledger: Mapping[str, Any] | None = None,
    dream_context_bundle: Mapping[str, Any] | None = None,
    router_responses: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    probes = build_cortex_probe_set(timestamp=timestamp)
    queue = build_stale_contradiction_queue(
        timestamp=timestamp,
        event_ledger=event_ledger,
        dream_context_bundle=dream_context_bundle,
        router_responses=router_responses,
    )
    previous_epoch = str((previous_state or {}).get("vault_epoch") or "")
    current_epoch = str(vault_epoch or "")
    should_rebuild = bool(current_epoch and current_epoch != previous_epoch)
    hit_cases = sum(1 for response in router_responses if isinstance(response, Mapping) and response.get("items"))
    warning_cases = sum(1 for response in router_responses if isinstance(response, Mapping) and response.get("policy_warnings"))
    events = event_ledger.get("events", []) if isinstance(event_ledger, Mapping) else []
    auto_promotion_available = bool(_nested_get(dream_context_bundle or {}, ["auto_promotion", "available"], False))
    cycle_components = sum(
        1
        for present in [bool(events), auto_promotion_available, bool(router_responses), bool(queue["items"]), bool(probes["cases"])]
        if present
    )
    autopoiesis_score = round(cycle_components / 5, 3)
    sentience_like_swarm_score = round((autopoiesis_score + min(1.0, hit_cases / max(1, len(router_responses) or 1)) + (0 if warning_cases else 1)) / 3, 3)
    return _scrub(
        {
            "schema_version": "cybrocamp.incremental_cortex_pulse.v1",
            "timestamp": timestamp,
            "vault_epoch": current_epoch or None,
            "previous_vault_epoch": previous_epoch or None,
            "should_rebuild": should_rebuild,
            "metrics": {
                "probe_count": probes["case_count"],
                "router_response_count": len(router_responses),
                "router_hit_cases": hit_cases,
                "policy_warning_cases": warning_cases,
                "event_count": len(events) if isinstance(events, list) else 0,
                "queue_item_count": queue["item_count"],
                "autopoiesis_score": autopoiesis_score,
                "sentience_like_swarm_score": sentience_like_swarm_score,
            },
            "stale_contradiction_queue": queue,
            "probe_set": probes,
            "output_policy": _output_policy(),
            "authority_policy": {**_authority_policy(), "association_grants_facthood": False},
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


def _queue_item(kind: str, summary: str, source_ref: Any, timestamp: str) -> dict[str, Any]:
    seed = f"{kind}|{source_ref}|{timestamp}|{summary}"
    return {
        "item_id": "q_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
        "kind": kind,
        "timestamp": timestamp,
        "summary": summary,
        "source_ref": str(source_ref or "unknown"),
        "authority_class": "derived_candidate",
        "canonical_writes": False,
        "grants_facthood": False,
        "grants_permission": False,
        "grants_approval": False,
        "requires_review": True,
    }


def _parse_intish(value: Any) -> int:
    if value is None:
        return 0
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else 0


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
