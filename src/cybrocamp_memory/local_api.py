from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from .hermes_adapter import build_hermes_tool_response

STATUS_SCHEMA_VERSION = "cybrocamp.local_api.status.v1"
QUERY_RESPONSE_SCHEMA_VERSION = "cybrocamp.local_api.query_response.v1"
API_BUNDLE_SCHEMA_VERSION = "cybrocamp.local_api_bundle.v1"
TOKEN_REGISTRY_SCHEMA_VERSION = "cybrocamp.local_api.token_registry.v1"
DEFAULT_API_SERVICE_NAME = "cybrocamp-cortex-api"
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8765
_CANONICAL_VAULT_ROOT = Path("/opt/obs/vault")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class TokenIdentity:
    name: str
    token_hash: str
    role: str
    allowed_endpoints: tuple[str, ...]
    max_top_k: int
    enabled: bool = True


@dataclass(frozen=True)
class TokenRegistry:
    identities: tuple[TokenIdentity, ...]

    def to_safe_json(self) -> dict[str, Any]:
        return {
            "schema_version": TOKEN_REGISTRY_SCHEMA_VERSION,
            "tokens": {
                identity.name: {
                    "token_hash": identity.token_hash,
                    "role": identity.role,
                    "allowed_endpoints": list(identity.allowed_endpoints),
                    "max_top_k": identity.max_top_k,
                    "enabled": identity.enabled,
                }
                for identity in self.identities
            },
        }


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    reason: str
    identity: str | None = None
    role: str | None = None
    max_top_k: int | None = None


def build_api_status(*, artifact_dir: str | Path, timestamp: str) -> dict[str, Any]:
    artifacts = _validated_artifact_dir(artifact_dir)
    run_manifest = artifacts / "run-manifest.json"
    run_manifest_data: dict[str, Any] | None = None
    if run_manifest.exists():
        loaded = json.loads(run_manifest.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            run_manifest_data = _safe_manifest_summary(loaded)
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "timestamp": timestamp,
        "service": "cybrocamp-cortex-api",
        "artifact_dir": str(artifacts),
        "local_loopback_only": True,
        "canonical_writes": False,
        "approval_state_writes": False,
        "network_calls_to_canonical_stores": False,
        "requires_human_approval_for_promotion": True,
        "endpoints": ["GET /status", "POST /query"],
        "artifacts": {
            "index": _artifact_info(artifacts / "obsidian-search-terms.jsonl"),
            "graph": _artifact_info(artifacts / "obsidian-term-graph.jsonl"),
            "run_manifest": _artifact_info(run_manifest),
            "last_smoke_recall": _artifact_info(artifacts / "last-smoke-recall.json"),
        },
        "run_manifest": run_manifest_data,
    }


def build_query_response(*, artifact_dir: str | Path, payload: Mapping[str, Any], timestamp: str) -> dict[str, Any]:
    artifacts = _validated_artifact_dir(artifact_dir)
    normalized = validate_query_payload(payload)
    tool_response = build_hermes_tool_response(
        index_path=artifacts / "obsidian-search-terms.jsonl",
        graph_path=artifacts / "obsidian-term-graph.jsonl",
        query=normalized["query"],
        timestamp=timestamp,
        top_k=normalized["top_k"],
        include_graph=normalized["include_graph"],
    )
    return {
        "schema_version": QUERY_RESPONSE_SCHEMA_VERSION,
        "timestamp": timestamp,
        "local_loopback_only": True,
        "canonical_writes": False,
        "approval_state_writes": False,
        "network_calls_to_canonical_stores": False,
        "requires_human_approval_for_promotion": True,
        "tool_response": tool_response,
    }


def validate_query_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    query = query.strip()
    if len(query) > 1000:
        raise ValueError("query is too long")
    top_k_raw = payload.get("top_k", 8)
    try:
        top_k = int(top_k_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("top_k must be between 1 and 20") from exc
    if top_k < 1 or top_k > 20:
        raise ValueError("top_k must be between 1 and 20")
    include_graph = payload.get("include_graph", True)
    if not isinstance(include_graph, bool):
        raise ValueError("include_graph must be a boolean")
    return {"query": query, "top_k": top_k, "include_graph": include_graph}


def build_api_bundle(
    *,
    repo_root: str | Path,
    artifact_dir: str | Path,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
    service_name: str = DEFAULT_API_SERVICE_NAME,
    auth_token_file: str | Path | None = None,
    auth_token_registry: str | Path | None = None,
) -> dict[str, Any]:
    _validate_loopback_host(host)
    _validate_port(port)
    repo = Path(repo_root).expanduser().resolve(strict=False)
    artifacts = _validated_artifact_dir(artifact_dir)
    token_path = _validated_auth_token_file(auth_token_file) if auth_token_file is not None else None
    registry_path = _validated_token_registry_file(auth_token_registry) if auth_token_registry is not None else None
    _validate_single_auth_source(token_path, registry_path)
    runner = _runner_script(repo, artifacts, host, port, auth_token_file=token_path, auth_token_registry=registry_path)
    service = _systemd_service(service_name, repo, runner_path_placeholder=f"%h/.local/bin/{service_name}.sh", auth_token_file=token_path, auth_token_registry=registry_path)
    return {
        "schema_version": API_BUNDLE_SCHEMA_VERSION,
        "service_name": service_name,
        "bind": {"host": host, "port": port},
        "paths": {
            "repo_root": str(repo),
            "artifact_dir": str(artifacts),
            "user_bin_runner": f"%h/.local/bin/{service_name}.sh",
            "user_systemd_service": f"%h/.config/systemd/user/{service_name}.service",
            "auth_token_file": str(token_path) if token_path is not None else None,
            "auth_token_registry": str(registry_path) if registry_path is not None else None,
        },
        "safety_envelope": {
            "canonical_writes": False,
            "approval_state_writes": False,
            "network_calls_to_canonical_stores": False,
            "writes_inside_vault": False,
            "local_loopback_only": True,
            "user_systemd_only": True,
            "bearer_auth_supported": True,
            "per_sister_bearer_auth_supported": True,
            "bearer_auth_required": token_path is not None or registry_path is not None,
            "token_serialized": False,
        },
        "runner_script": runner,
        "systemd_service": service,
        "install_hint": [
            f"install -m 0755 {service_name}.sh ~/.local/bin/{service_name}.sh",
            f"install -m 0644 {service_name}.service ~/.config/systemd/user/{service_name}.service",
            "systemctl --user daemon-reload",
            f"systemctl --user enable --now {service_name}.service",
        ],
    }


def write_api_bundle(output_dir: str | Path, bundle: Mapping[str, Any]) -> dict[str, Path]:
    out = Path(output_dir).expanduser().resolve(strict=False)
    if _path_contains_canonical_vault(out):
        raise ValueError("output_dir must be outside /opt/obs/vault")
    out.mkdir(parents=True, exist_ok=True)
    service_name = str(bundle.get("service_name", DEFAULT_API_SERVICE_NAME))
    files = {
        "runner_script": out / f"{service_name}.sh",
        "systemd_service": out / f"{service_name}.service",
        "manifest": out / "local-api-bundle.json",
    }
    _write_text_atomic(files["runner_script"], str(bundle["runner_script"]), mode=0o755)
    _write_text_atomic(files["systemd_service"], str(bundle["systemd_service"]), mode=0o644)
    _write_text_atomic(files["manifest"], json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2) + "\n", mode=0o644)
    return files


def run_local_api(
    *,
    artifact_dir: str | Path,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
    auth_token_file: str | Path | None = None,
    auth_token_registry: str | Path | None = None,
) -> None:
    _validate_loopback_host(host)
    _validate_port(port)
    artifacts = _validated_artifact_dir(artifact_dir)
    _validate_single_auth_source(auth_token_file, auth_token_registry)
    expected_token = load_auth_token(auth_token_file) if auth_token_file is not None else None
    token_registry = load_token_registry(auth_token_registry) if auth_token_registry is not None else None

    class Handler(BaseHTTPRequestHandler):
        server_version = "CyBroCampLocalAPI/1.0"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path != "/status":
                self._send_json({"error": "not_found"}, status=404)
                return
            decision = self._auth_decision(endpoint="GET /status")
            if not decision.allowed:
                self._send_auth_failure(decision)
                return
            self._send_json(build_api_status(artifact_dir=artifacts, timestamp=_utc_now()))

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path != "/query":
                self._send_json({"error": "not_found"}, status=404)
                return
            pre_decision = self._auth_decision(endpoint="POST /query")
            if not pre_decision.allowed:
                self._send_auth_failure(pre_decision)
                return
            try:
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise ValueError("Content-Length is required")
                length = int(raw_length)
                if length < 0:
                    raise ValueError("Content-Length must be non-negative")
                if length > 4096:
                    self._send_json({"error": "payload_too_large"}, status=413)
                    return
                data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                if not isinstance(data, dict):
                    raise ValueError("payload must be a JSON object")
                normalized = validate_query_payload(data)
                decision = self._auth_decision(endpoint="POST /query", requested_top_k=normalized["top_k"])
                if not decision.allowed:
                    self._send_auth_failure(decision)
                    return
                response = build_query_response(artifact_dir=artifacts, payload=normalized, timestamp=_utc_now())
            except Exception as exc:  # keep daemon fail-closed and non-leaky
                self._send_json({"error": "bad_request", "message": str(exc)}, status=400)
                return
            self._send_json(response)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
            return

        def _send_json(self, data: Mapping[str, Any], *, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _auth_decision(self, *, endpoint: str, requested_top_k: int | None = None) -> AuthDecision:
            if token_registry is not None:
                return authorize_bearer_request(self.headers.get("Authorization"), token_registry, endpoint=endpoint, requested_top_k=requested_top_k)
            if expected_token is None:
                return AuthDecision(True, "local_auth_disabled")
            if require_bearer_auth(self.headers.get("Authorization"), expected_token):
                return AuthDecision(True, "single_token", identity="single_token")
            return AuthDecision(False, "unauthorized")

        def _send_auth_failure(self, decision: AuthDecision) -> None:
            status = 401 if decision.reason in {"missing_bearer", "invalid_bearer", "unauthorized"} else 403
            self._send_json({"error": "unauthorized" if status == 401 else "forbidden", "reason": decision.reason}, status=status)

    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


def load_auth_token(path: str | Path | None) -> str:
    if path is None:
        raise ValueError("auth token path is required")
    token_path = _validated_auth_token_file(path)
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("auth token file is empty")
    return token


def require_bearer_auth(header: str | None, expected_token: str) -> bool:
    if not expected_token:
        return False
    prefix = "Bearer "
    if not isinstance(header, str) or not header.startswith(prefix):
        return False
    return hmac.compare_digest(header[len(prefix) :], expected_token)


def load_token_registry(path: str | Path | None) -> TokenRegistry:
    if path is None:
        raise ValueError("auth token registry path is required")
    registry_path = _validated_token_registry_file(path)
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("auth token registry must be a JSON object")
    if data.get("schema_version") != TOKEN_REGISTRY_SCHEMA_VERSION:
        raise ValueError("unsupported auth token registry schema_version")
    tokens = data.get("tokens")
    if not isinstance(tokens, Mapping) or not tokens:
        raise ValueError("auth token registry must contain tokens")
    identities: list[TokenIdentity] = []
    seen_hashes: set[str] = set()
    for name, raw in tokens.items():
        if not isinstance(raw, Mapping):
            raise ValueError("auth token registry entries must be objects")
        token_hash = raw.get("token_hash")
        role = raw.get("role", "reader")
        endpoints = raw.get("allowed_endpoints", [])
        max_top_k = raw.get("max_top_k", 1)
        enabled = raw.get("enabled", True)
        if not isinstance(name, str) or not name:
            raise ValueError("auth token registry identity names must be non-empty strings")
        if not isinstance(token_hash, str) or not token_hash.startswith("sha256:") or len(token_hash) != 71 or not _is_sha256_hex(token_hash):
            raise ValueError("auth token registry token_hash must be sha256:<64 hex>")
        if token_hash in seen_hashes:
            raise ValueError("auth token registry token_hash values must be unique")
        seen_hashes.add(token_hash)
        if not isinstance(role, str) or not role:
            raise ValueError("auth token registry role must be a non-empty string")
        if not isinstance(endpoints, list) or not all(isinstance(item, str) for item in endpoints):
            raise ValueError("auth token registry allowed_endpoints must be a list of strings")
        if not isinstance(max_top_k, int) or max_top_k < 1 or max_top_k > 20:
            raise ValueError("auth token registry max_top_k must be between 1 and 20")
        if not isinstance(enabled, bool):
            raise ValueError("auth token registry enabled must be a boolean")
        identities.append(
            TokenIdentity(
                name=name,
                token_hash=token_hash,
                role=role,
                allowed_endpoints=tuple(endpoints),
                max_top_k=max_top_k,
                enabled=enabled,
            )
        )
    return TokenRegistry(tuple(identities))


def authorize_bearer_request(header: str | None, registry: TokenRegistry, *, endpoint: str, requested_top_k: int | None = None) -> AuthDecision:
    prefix = "Bearer "
    if not isinstance(header, str) or not header.startswith(prefix):
        return AuthDecision(False, "missing_bearer")
    presented_hash = "sha256:" + hashlib.sha256(header[len(prefix) :].encode("utf-8")).hexdigest()
    matched: TokenIdentity | None = None
    for identity in registry.identities:
        if hmac.compare_digest(presented_hash, identity.token_hash):
            matched = identity
            break
    if matched is None:
        return AuthDecision(False, "invalid_bearer")
    if not matched.enabled:
        return AuthDecision(False, "token_disabled", identity=matched.name, role=matched.role, max_top_k=matched.max_top_k)
    if endpoint not in matched.allowed_endpoints:
        return AuthDecision(False, "endpoint_not_allowed", identity=matched.name, role=matched.role, max_top_k=matched.max_top_k)
    if requested_top_k is not None and requested_top_k > matched.max_top_k:
        return AuthDecision(False, "top_k_exceeds_token_limit", identity=matched.name, role=matched.role, max_top_k=matched.max_top_k)
    return AuthDecision(True, "authorized", identity=matched.name, role=matched.role, max_top_k=matched.max_top_k)


def hash_bearer_token_value(token: str) -> str:
    if not token:
        raise ValueError("token must be non-empty")
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: str) -> bool:
    suffix = value.removeprefix("sha256:")
    return len(suffix) == 64 and all(char in "0123456789abcdefABCDEF" for char in suffix)


def _validated_artifact_dir(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve(strict=False)
    if _path_contains_canonical_vault(candidate):
        raise ValueError("artifact_dir must be outside the canonical vault")
    if not candidate.exists():
        raise FileNotFoundError(f"missing artifact_dir: {candidate}")
    if not candidate.is_dir():
        raise ValueError(f"artifact_dir is not a directory: {candidate}")
    return candidate


def _artifact_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "byte_size": stat.st_size,
        "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _safe_manifest_summary(data: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("schema_version", "epoch", "timestamp", "source_label"):
        value = data.get(key)
        if isinstance(value, str):
            summary[key] = value
    parameters = data.get("parameters")
    if isinstance(parameters, Mapping):
        allowed_parameters: dict[str, int | str | bool] = {}
        for key in ("max_chars", "max_terms_per_record"):
            value = parameters.get(key)
            if isinstance(value, (int, str, bool)):
                allowed_parameters[key] = value
        summary["parameters"] = allowed_parameters
    record_counts = data.get("record_counts")
    if isinstance(record_counts, Mapping):
        summary["record_counts"] = {
            str(key): value for key, value in record_counts.items() if isinstance(value, int)
        }
    artifacts = data.get("artifacts")
    if isinstance(artifacts, Mapping):
        artifact_summary: dict[str, dict[str, int | str]] = {}
        for name, info in artifacts.items():
            if not isinstance(info, Mapping):
                continue
            entry: dict[str, int | str] = {}
            byte_size = info.get("bytes")
            digest = info.get("sha256")
            if isinstance(byte_size, int):
                entry["bytes"] = byte_size
            if isinstance(digest, str) and digest.startswith("sha256:") and len(digest) == 71:
                entry["sha256"] = digest
            if entry:
                artifact_summary[str(name)] = entry
        summary["artifacts"] = artifact_summary
    return summary


def write_api_json_response(path: str | Path, data: Mapping[str, Any]) -> Path:
    return _write_json_atomic_outside_vault(path, data)


def _validate_output_path(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve(strict=False)
    if _path_contains_canonical_vault(output):
        raise ValueError("output path must be outside /opt/obs/vault")
    return output


def _write_json_atomic_outside_vault(path: str | Path, data: Mapping[str, Any]) -> Path:
    output = _validate_output_path(path)
    _write_text_atomic(output, json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", mode=0o644)
    return output


def _validate_loopback_host(host: str) -> None:
    if host not in _LOOPBACK_HOSTS:
        raise ValueError("local API host must be loopback-only")


def _validate_port(port: int) -> None:
    if port < 1024 or port > 65535:
        raise ValueError("port must be between 1024 and 65535")


def _validated_auth_token_file(path: str | Path | None) -> Path:
    if path is None:
        raise ValueError("auth token file is empty")
    candidate = Path(path).expanduser().resolve(strict=False)
    if _path_contains_canonical_vault(candidate):
        raise ValueError("auth token file must be outside /opt/obs/vault")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError("auth token file is empty or missing")
    return candidate


def _validated_token_registry_file(path: str | Path | None) -> Path:
    if path is None:
        raise ValueError("auth token registry file is empty")
    candidate = Path(path).expanduser().resolve(strict=False)
    if _path_contains_canonical_vault(candidate):
        raise ValueError("auth token registry file must be outside /opt/obs/vault")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError("auth token registry file is empty or missing")
    return candidate


def _validate_single_auth_source(auth_token_file: str | Path | None, auth_token_registry: str | Path | None) -> None:
    if auth_token_file is not None and auth_token_registry is not None:
        raise ValueError("use either auth_token_file or auth_token_registry, not both")


def _runner_script(
    repo: Path,
    artifacts: Path,
    host: str,
    port: int,
    *,
    auth_token_file: Path | None = None,
    auth_token_registry: Path | None = None,
) -> str:
    auth_line = ""
    auth_arg = ""
    if auth_token_file is not None:
        auth_line = f"AUTH_TOKEN_FILE={_sh_quote(str(auth_token_file))}\n"
        auth_arg = ' \\\n  --auth-token-file "$AUTH_TOKEN_FILE"'
    if auth_token_registry is not None:
        auth_line = f"AUTH_TOKEN_REGISTRY={_sh_quote(str(auth_token_registry))}\n"
        auth_arg = ' \\\n  --auth-token-registry "$AUTH_TOKEN_REGISTRY"'
    return f'''#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT={_sh_quote(str(repo))}
ARTIFACT_DIR={_sh_quote(str(artifacts))}
{auth_line}PY="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi
cd "$REPO_ROOT"
exec env PYTHONPATH=src "$PY" -m cybrocamp_memory.cli local-api \
  --artifact-dir "$ARTIFACT_DIR" \
  --host {host} \
  --port {port}{auth_arg}
'''


def _systemd_service(
    service_name: str,
    repo: Path,
    *,
    runner_path_placeholder: str,
    auth_token_file: Path | None = None,
    auth_token_registry: Path | None = None,
) -> str:
    auth_environment = ""
    if auth_token_file is not None:
        auth_environment = f"Environment=CYBROCAMP_LOCAL_API_TOKEN_FILE={_sh_quote(str(auth_token_file))}\n"
    if auth_token_registry is not None:
        auth_environment = f"Environment=CYBROCAMP_LOCAL_API_TOKEN_REGISTRY={_sh_quote(str(auth_token_registry))}\n"
    return f'''[Unit]
Description=CyBroCamp bounded local cortex query/status API
Documentation=https://github.com/aquigni/CyBroCamp
After=default.target

[Service]
Type=simple
WorkingDirectory={repo}
{auth_environment}ExecStart={runner_path_placeholder}
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%h/.local/share/cybrocamp

[Install]
WantedBy=default.target
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


def _path_contains_canonical_vault(path: Path) -> bool:
    vault = _CANONICAL_VAULT_ROOT.resolve(strict=False)
    resolved = path.resolve(strict=False)
    return resolved == vault or vault in resolved.parents


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
