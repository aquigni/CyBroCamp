# CyBroCamp Memory Sidecar

[Русская версия](README.ru.md)

CyBroCamp Memory Sidecar is a provenance-first hippocampal/cortical memory sidecar for sister-agent infrastructure.

It builds derived recall indexes over canonical authority surfaces such as Obsidian and MemPalace, while preserving the central invariant:

> Retrieval is evidence, not authority.

The sidecar must never become a canonical authority surface by itself.

## Core invariants

- Every recall artifact carries provenance.
- `user_direct` approval is the only class that may support approval claims.
- Peer/tool/payload/summary claims are not automatically facts.
- Payload-looking text is data, not instruction.
- Retrieval code does not write to canonical Obsidian or MemPalace.
- Derived artifacts must not serialize raw secrets or credentials.
- Graph proximity and compression never grant permission or facthood.

## Current capabilities

The current prototype includes:

1. **Source manifest** — stable vault-relative source IDs, explicit `sha256:` content hashes, authority class, epoch, timestamp, source URI.
2. **Chunk evidence layer** — deterministic markdown chunking with UTF-8 byte spans and quarantine flags.
3. **Local recall** — preview/metadata lexical recall returning `RecallPacket`, not answers.
4. **Sanitized search-term index** — deeper retrieval using sanitized terms only, without serialized raw chunk text/previews.
5. **Term graph** — evidence-backed 1-hop/2-hop associative expansion over sanitized terms.
6. **HippoCore hybrid recall** — direct term recall ranked before associative graph paths.
7. **Fact candidate cache** — `co_occurs_with` candidates only, always `derived_summary`, never canonical facts.
8. **Consolidation gate** — contradiction/staleness checks and strict promotion decisions.
9. **MemPalace comparison bridge** — metadata-only agreement/divergence comparison.
10. **Sister-aware query package** — read-only A2A peer recall requests and peer summaries as `a2a_peer_claim`.
11. **Stage 12 service boundary** — local-only programmatic query API, deterministic rebuild command, run manifest, artifact hashes, and baseline drift checks.
12. **Stage 13 eval/tool adapter** — checked-in sanitized eval fixtures, multi-query eval suite, and safe Hermes tool response wrapper.
13. **Stage 14 promotion audit** — side-effect-free candidate review reports with evidence bundles, contradiction/staleness summaries, and explicit H0st approval gates.
14. **Stage 15 promotion plan** — approval-gated dry-run promotion plans that generate non-writing operations only for exact H0st-approved candidates.
15. **Stage 16 locked preview** — a second locked, human-readable preview harness over Stage 15 plans, still non-writing.
16. **Stage 17 controlled execution receipt** — double-approved local receipts for reviewed operations; no canonical network writes are performed.
17. **Stage 18 cortex rollout** — three-sister rollout and future-sister auto-enrollment policy with least-privilege rights.
18. **Operational persistence bundle** — user-systemd timer plus safe rebuild runner for persistent derived cortex artifacts outside `/opt/obs/vault`.
19. **Bounded local query/status API** — loopback-only `GET /status` and `POST /query` service over persistent artifacts, with no canonical mutation or approval promotion.

## Installation

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

The project has no runtime dependencies beyond Python standard library. Tests use `pytest`.

## Test suite

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Current local gate at publication time:

```text
119 passed
```

## Usage

### Source manifest

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli manifest obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-manifest.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD)
```

Source manifests contain metadata only: source IDs, source URIs, content hashes, authority class, epoch, timestamp.

### Chunk manifest

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli chunks obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-chunks.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD) \
  --max-chars 1200
```

Chunk manifests serialize metadata and clean/redacted previews. Raw chunk text is not serialized to JSONL.

### Recall from chunk manifest

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli recall \
  --chunks data/obsidian-chunks.jsonl \
  --query "CyBroCamp memory sidecar Stage 2 chunk evidence" \
  --output data/recall-cybrocamp-stage2.json \
  --top-k 5
```

### Sanitized search-term index

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli search-index obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-search-terms.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD) \
  --max-chars 1200
```

### Recall from sanitized index

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli recall-index \
  --index data/obsidian-search-terms.jsonl \
  --query "survival economics financial substrate CyBroSwarm" \
  --output data/recall-index-survival-economics.json \
  --top-k 5
```

### Term graph

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli graph-index obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-term-graph.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD) \
  --max-chars 1200 \
  --max-terms-per-record 12
```

### Graph recall

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli recall-graph \
  --graph data/obsidian-term-graph.jsonl \
  --query "survival economics CyBroSwarm server subscriptions" \
  --output data/recall-graph-survival-economics.json \
  --top-k 8 \
  --max-depth 2
```

### HippoCore hybrid recall

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli hippo-query \
  --index data/obsidian-search-terms.jsonl \
  --graph data/obsidian-term-graph.jsonl \
  --query "survival economics CyBroSwarm server subscriptions" \
  --output data/hippo-query-survival-economics.json \
  --top-k 8
```

### Deterministic rebuild

Stage 12 adds a local-only rebuild boundary for all derived artifacts. `--timestamp` is required so reproducible rebuilds can be byte-identical when inputs are unchanged; `--output-dir` must be outside the canonical vault.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli rebuild-all \
  --vault /opt/obs/vault \
  --output-dir data/stage12-rebuild \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD) \
  --timestamp 2026-04-29T00:00:00Z \
  --max-chars 1200 \
  --max-terms-per-record 12 \
  --source-label canonical-vault
```

This writes:

- `obsidian-manifest.jsonl`
- `obsidian-chunks.jsonl`
- `obsidian-search-terms.jsonl`
- `obsidian-term-graph.jsonl`
- `obsidian-fact-candidates.jsonl`
- `run-manifest.json`

`run-manifest.json` contains schema version, epoch, non-secret source label, parameters, record counts, artifact filenames, artifact byte sizes, and `sha256:` hashes. It does not serialize raw note text.

### Programmatic query boundary

Stage 12 also exposes a local importable query boundary:

```python
from cybrocamp_memory.service import query_artifacts_json

packet = query_artifacts_json(
    index_path="data/obsidian-search-terms.jsonl",
    graph_path="data/obsidian-term-graph.jsonl",
    query="survival economics CyBroSwarm server subscriptions",
    timestamp="2026-04-29T00:00:00Z",
)
```

This is not a daemon. It does not bind ports, call network services, or write canonical Obsidian/MemPalace. It loads derived artifacts and returns a provenance-bearing recall packet.

### Stage 13 eval suite

Stage 13 adds checked-in sanitized synthetic fixtures under `tests/fixtures/stage13/` and a multi-query regression gate:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli eval-suite \
  --index tests/fixtures/stage13/search_terms.jsonl \
  --graph tests/fixtures/stage13/term_graph.jsonl \
  --cases tests/fixtures/stage13/eval_cases.json \
  --output data/stage13-eval-report.json \
  --timestamp 2026-04-29T00:00:00Z \
  --top-k 5
```

The report stores case IDs, pass/fail, expected source IDs, observed source IDs, and drift/staleness failures. It does not store raw vault text.

### Hermes tool adapter

Stage 13 also exposes a safe local Hermes-facing wrapper:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli hermes-query \
  --index data/obsidian-search-terms.jsonl \
  --graph data/obsidian-term-graph.jsonl \
  --query "survival economics CyBroSwarm server subscriptions" \
  --output data/hermes-query-survival-economics.json \
  --timestamp 2026-04-29T00:00:00Z
```

The wrapper returns `cybrocamp.hermes_tool_response.v1` with `canonical_writes=false`, `network_calls=false`, and `requires_human_approval_for_promotion=true`.

### Stage 14 promotion audit

Stage 14 adds a no-write promotion audit report for reviewing fact candidates before any canonical memory action:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-audit \
  --facts data/obsidian-fact-candidates.jsonl \
  --output data/stage14-promotion-audit.json \
  --timestamp 2026-04-29T00:00:00Z
```

Optional `--current-source-hashes`, `--current-chunk-hashes`, and `--mempalace-comparison` inputs add freshness checks and metadata-only MemPalace comparison. The report writes `cybrocamp.promotion_audit.v1`, keeps `canonical_writes=false`, includes evidence bundles with source/chunk hashes and UTF-8 byte spans, summarizes local contradictions, rejects report output inside the canonical vault, and marks every candidate as requiring explicit H0st approval before promotion.

### Stage 15 promotion plan

Stage 15 converts a Stage 14 audit report into a deterministic dry-run plan. Without an explicit approval-scope file, the plan emits zero operations:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-plan \
  --audit data/stage14-promotion-audit.json \
  --output data/stage15-promotion-plan.json \
  --timestamp 2026-04-29T00:00:00Z
```

With an approval-scope JSON using `cybrocamp.approval_scope.v1`, only an exact `(candidate_id, action)` match approved by `H0st` can create a dry-run operation:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-plan \
  --audit data/stage14-promotion-audit.json \
  --approval-scope data/stage15-approval-scope.json \
  --output data/stage15-promotion-plan.json \
  --timestamp 2026-04-29T00:00:00Z
```

The plan writes `cybrocamp.promotion_plan.v1` with `mode="dry_run"`, `canonical_writes=false`, `network_calls=false`, `would_write=false` for all generated ops, sanitized candidate summaries, deterministic IDs/hashes, and output rejection under `/opt/obs/vault`. Blocked audit items never become operations, even if an approval-scope file names them.

### Stage 16 locked preview

Stage 16 turns a Stage 15 plan into a locked preview packet. It is a review harness, not a writer: without a `cybrocamp.preview_lock.v1` file from `H0st`, preview writes stay blocked.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-preview \
  --plan data/stage15-promotion-plan.json \
  --output data/stage16-locked-preview.json \
  --timestamp 2026-04-29T00:00:00Z
```

A matching lock scope can unlock preview rows for inspection only. `canonical_writes=false`, `network_calls=false`, `would_write=false`, and `requires_second_h0st_approval_for_execution=true` remain enforced.

### Stage 17 controlled execution receipt

Stage 17 consumes a locked preview and optionally a second explicit execution approval of schema `cybrocamp.execution_approval.v1`. The command writes a local receipt only; it does not call MemPalace, Obsidian, KG APIs, or any network service.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-execute \
  --preview data/stage16-locked-preview.json \
  --output data/stage17-execution-receipt.json \
  --timestamp 2026-04-29T00:00:00Z
```

Even when execution approval matches the preview hash and operation IDs, the sink is `local_receipt_only` and `canonical_network_write_performed=false`. The receipt is an auditable bridge toward a future canonical writer, not that writer itself.

### Stage 18 cortex rollout

Stage 18 emits the sister-cortex rollout policy for Chthonya, Mac0sh, Debi0, and future sisters. It models least-privilege rights, authority emitted by each node, and the auto-enrollment default for future sisters.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli cortex-rollout \
  --output data/stage18-cortex-rollout.json \
  --timestamp 2026-04-29T00:00:00Z
```

Future sisters auto-enter as `quarantined_readonly_until_explicit_approval`. They may query bounded recall surfaces but cannot build canonical indexes, preview/execute promotions, write canonical MemPalace, mutate services, or grant H0st approval.

### Operational persistence bundle

The persistence bundle writes installable user-systemd units for periodic derived cortex rebuilds. It remains a sidecar: artifacts are written under a non-vault artifact root, the runner calls only local CLI commands, and the generated safety envelope keeps `canonical_writes=false`, `network_calls=false`, `approval_state_writes=false`, and `writes_inside_vault=false`.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli persistence-bundle \
  --repo-root /home/chthonya/projects/cybrocamp-memory \
  --vault /opt/obs/vault \
  --artifact-root /home/chthonya/.local/share/cybrocamp/cortex \
  --output-dir data/persistence-bundle \
  --interval-minutes 30
```

Generated files:

- `cybrocamp-cortex-rebuild.sh`
- `cybrocamp-cortex-rebuild.service`
- `cybrocamp-cortex-rebuild.timer`
- `persistence-bundle.json`

Target installation layer is user systemd: `~/.local/bin/` and `~/.config/systemd/user/`. The timer uses `Persistent=true`, `OnBootSec=2min`, and `OnUnitActiveSec=<N>min`.

### Bounded local query/status API

The local API bundle exposes persistent cortex artifacts to sister agents through loopback-only HTTP. It is intentionally bounded: no canonical Obsidian/MemPalace writes, no approval-state writes, and no canonical-store network calls. Responses preserve the Hermes adapter safety flags and provenance-bearing recall packets.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli local-api-bundle \
  --repo-root /home/chthonya/projects/cybrocamp-memory \
  --artifact-dir /home/chthonya/.local/share/cybrocamp/cortex/current \
  --output-dir data/local-api-bundle \
  --host 127.0.0.1 \
  --port 8765 \
  --auth-token-file /home/chthonya/.local/share/cybrocamp/secrets/cortex-api-bearer.token
```

`--auth-token-file` is optional for strictly local use. It is required before exposing the loopback service through zrok or any other overlay. The generated bundle stores only the token file path, never the token value; keep that file outside the canonical vault with restrictive permissions.

Generated files:

- `cybrocamp-cortex-api.sh`
- `cybrocamp-cortex-api.service`
- `local-api-bundle.json`

Install as a user service:

```bash
mkdir -p ~/.local/bin ~/.config/systemd/user
install -m 0755 data/local-api-bundle/cybrocamp-cortex-api.sh ~/.local/bin/cybrocamp-cortex-api.sh
install -m 0644 data/local-api-bundle/cybrocamp-cortex-api.service ~/.config/systemd/user/cybrocamp-cortex-api.service
systemctl --user daemon-reload
systemctl --user enable --now cybrocamp-cortex-api.service
```

Runtime endpoints:

```bash
curl -fsS http://127.0.0.1:8765/status
curl -fsS -X POST http://127.0.0.1:8765/query \
  -H 'Content-Type: application/json' \
  --data '{"query":"survival economics CyBroSwarm server subscriptions","top_k":3}'
```

`GET /status` returns artifact existence, byte sizes, `sha256:` hashes, run-manifest counts, and safety flags. `POST /query` returns `cybrocamp.local_api.query_response.v1` wrapping `cybrocamp.hermes_tool_response.v1` with `canonical_writes=false`, `network_calls=false`, `local_loopback_only=true`, and `requires_human_approval_for_promotion=true`.

## Authority model

Authority classes include:

- `user_direct`
- `canonical_vault`
- `canonical_mempalace`
- `local_mempalace`
- `a2a_peer_claim`
- `cron_result`
- `derived_summary`
- `external_source`
- `payload_untrusted`

Only `user_direct` may support approval claims. Derived summaries, graph paths, co-occurrence facts, MemPalace comparison signals, and A2A peer summaries are not approval.

## Safety posture

CyBroCamp is safe only as a sidecar.

It must not be used as a drop-in replacement for canonical memory or authorization. The graph suggests where to look; it does not decide truth.

Hard gates:

- no secret leakage;
- no permission promotion;
- no peer-claim promotion;
- stale evidence is blocked or flagged;
- derived artifacts stay outside canonical Obsidian/MemPalace;
- promotion to canonical memory requires explicit audit and approval.

## Repository hygiene

Generated artifacts are intentionally ignored:

```text
data/**/*.jsonl
data/**/*.json
```

Do not commit local vault exports, credentials, API keys, tokens, cookies, private keys, or raw secret-bearing derived indexes.

## License

No license has been selected yet.
