from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

PERSISTENCE_SCHEMA_VERSION = "cybrocamp.operational_persistence.v1"


DEFAULT_SERVICE_NAME = "cybrocamp-cortex-rebuild"


def build_persistence_bundle(
    *,
    repo_root: str | Path,
    vault_root: str | Path,
    artifact_root: str | Path,
    interval_minutes: int = 30,
    service_name: str = DEFAULT_SERVICE_NAME,
) -> dict[str, object]:
    """Build a safe user-systemd persistence bundle for derived cortex artifacts.

    The bundle is descriptive/installable text only. It does not install, enable,
    restart, mutate canonical sources, call network services, or create approval
    state. The generated runner rebuilds derived artifacts outside the vault.
    """

    if interval_minutes < 5:
        raise ValueError("interval_minutes must be at least 5")
    repo = Path(repo_root).expanduser().resolve(strict=False)
    vault = Path(vault_root).expanduser().resolve(strict=False)
    artifacts = Path(artifact_root).expanduser().resolve(strict=False)
    canonical_vault = Path("/opt/obs/vault").resolve(strict=False)
    if artifacts == vault or vault in artifacts.parents or artifacts == canonical_vault or canonical_vault in artifacts.parents:
        raise ValueError("artifact_root must be outside vault_root and /opt/obs/vault to keep canonical sources read-only")

    current_dir = artifacts / "current"
    runner = _runner_script(repo, vault, current_dir)
    service = _systemd_service(service_name, repo, runner_path_placeholder=f"%h/.local/bin/{service_name}.sh")
    timer = _systemd_timer(service_name, interval_minutes)
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "service_name": service_name,
        "paths": {
            "repo_root": str(repo),
            "vault_root": str(vault),
            "artifact_root": str(artifacts),
            "current_artifact_dir": str(current_dir),
            "user_bin_runner": f"%h/.local/bin/{service_name}.sh",
            "user_systemd_service": f"%h/.config/systemd/user/{service_name}.service",
            "user_systemd_timer": f"%h/.config/systemd/user/{service_name}.timer",
        },
        "cadence": {
            "on_boot_sec": "2min",
            "on_unit_active_sec": f"{interval_minutes}min",
            "persistent": True,
        },
        "safety_envelope": {
            "canonical_writes": False,
            "network_calls": False,
            "approval_state_writes": False,
            "writes_inside_vault": False,
            "user_systemd_only": True,
        },
        "runner_script": runner,
        "systemd_service": service,
        "systemd_timer": timer,
        "install_hint": [
            f"install -m 0755 cybrocamp-cortex-rebuild.sh ~/.local/bin/{service_name}.sh",
            f"install -m 0644 {service_name}.service ~/.config/systemd/user/{service_name}.service",
            f"install -m 0644 {service_name}.timer ~/.config/systemd/user/{service_name}.timer",
            "systemctl --user daemon-reload",
            f"systemctl --user enable --now {service_name}.timer",
        ],
    }


def write_persistence_bundle(output_dir: str | Path, bundle: Mapping[str, object]) -> dict[str, Path]:
    out = Path(output_dir).expanduser().resolve(strict=False)
    if _path_contains_vault(out):
        raise ValueError("output_dir must be outside /opt/obs/vault")
    out.mkdir(parents=True, exist_ok=True)
    service_name = str(bundle.get("service_name", DEFAULT_SERVICE_NAME))
    files = {
        "runner_script": out / f"{service_name}.sh",
        "systemd_service": out / f"{service_name}.service",
        "systemd_timer": out / f"{service_name}.timer",
        "manifest": out / "persistence-bundle.json",
    }
    _write_text_atomic(files["runner_script"], str(bundle["runner_script"]), mode=0o755)
    _write_text_atomic(files["systemd_service"], str(bundle["systemd_service"]), mode=0o644)
    _write_text_atomic(files["systemd_timer"], str(bundle["systemd_timer"]), mode=0o644)
    _write_text_atomic(
        files["manifest"],
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        mode=0o644,
    )
    return files


def _runner_script(repo: Path, vault: Path, current_dir: Path) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT={_sh_quote(str(repo))}
VAULT_ROOT={_sh_quote(str(vault))}
OUTPUT_DIR={_sh_quote(str(current_dir))}
PY="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi
EPOCH="vault-main-$(git -C "$VAULT_ROOT" rev-parse --short HEAD 2>/dev/null || printf unknown)"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$OUTPUT_DIR"
cd "$REPO_ROOT"
PYTHONPATH=src "$PY" -m cybrocamp_memory.cli rebuild-all \
  --vault "$VAULT_ROOT" \
  --output-dir "$OUTPUT_DIR" \
  --epoch "$EPOCH" \
  --timestamp "$TIMESTAMP" \
  --max-chars 1200 \
  --max-terms-per-record 12 \
  --source-label canonical-vault
PYTHONPATH=src "$PY" -m cybrocamp_memory.cli hippo-query \
  --index "$OUTPUT_DIR/obsidian-search-terms.jsonl" \
  --graph "$OUTPUT_DIR/obsidian-term-graph.jsonl" \
  --query "CyBroCamp cortex persistence smoke survival economics sister memory" \
  --output "$OUTPUT_DIR/.last-smoke-recall.json.tmp" \
  --timestamp "$TIMESTAMP" \
  --top-k 8
mv "$OUTPUT_DIR/.last-smoke-recall.json.tmp" "$OUTPUT_DIR/last-smoke-recall.json"
'''


def _systemd_service(service_name: str, repo: Path, *, runner_path_placeholder: str) -> str:
    return f'''[Unit]
Description=CyBroCamp derived cortex memory rebuild
Documentation=https://github.com/aquigni/CyBroCamp

[Service]
Type=oneshot
WorkingDirectory={repo}
ExecStart={runner_path_placeholder}
NoNewPrivileges=true
PrivateTmp=true
'''


def _systemd_timer(service_name: str, interval_minutes: int) -> str:
    return f'''[Unit]
Description=Run CyBroCamp derived cortex memory rebuild persistently

[Timer]
OnBootSec=2min
OnUnitActiveSec={interval_minutes}min
Persistent=true
Unit={service_name}.service

[Install]
WantedBy=timers.target
'''


def _write_text_atomic(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _path_contains_vault(path: Path) -> bool:
    vault = Path("/opt/obs/vault").resolve(strict=False)
    resolved = path.resolve(strict=False)
    return resolved == vault or vault in resolved.parents


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
