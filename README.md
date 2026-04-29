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
59 passed
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
