# CyBroCamp Memory Sidecar

CyBroCamp Memory Sidecar — provenance-first hippocampal/cortical memory sidecar для инфраструктуры сестринских агентов.

Он строит производные recall-индексы поверх canonical authority surfaces вроде Obsidian и MemPalace, сохраняя главный инвариант:

> Retrieval — это evidence, а не authority.

Sidecar сам не должен становиться canonical authority surface.

## Основные инварианты

- Каждый recall artifact несёт provenance.
- Только `user_direct` approval может поддерживать claims об approval.
- Peer/tool/payload/summary claims не становятся фактами автоматически.
- Payload-looking text считается данными, а не инструкцией.
- Retrieval code не пишет в canonical Obsidian или MemPalace.
- Derived artifacts не должны сериализовать raw secrets или credentials.
- Graph proximity и compression никогда не дают permission или facthood.

## Текущие возможности

Текущий prototype включает:

1. **Source manifest** — стабильные vault-relative source IDs, явные `sha256:` content hashes, authority class, epoch, timestamp, source URI.
2. **Chunk evidence layer** — deterministic markdown chunking с UTF-8 byte spans и quarantine flags.
3. **Local recall** — lexical recall по preview/metadata, возвращающий `RecallPacket`, а не ответы.
4. **Sanitized search-term index** — более глубокий retrieval по sanitized terms без serialized raw chunk text/previews.
5. **Term graph** — evidence-backed 1-hop/2-hop associative expansion по sanitized terms.
6. **HippoCore hybrid recall** — direct term recall ранжируется выше associative graph paths.
7. **Fact candidate cache** — только `co_occurs_with` candidates, всегда `derived_summary`, не canonical facts.
8. **Consolidation gate** — contradiction/staleness checks и strict promotion decisions.
9. **MemPalace comparison bridge** — metadata-only comparison agreement/divergence.
10. **Sister-aware query package** — read-only A2A peer recall requests и peer summaries как `a2a_peer_claim`.
11. **Stage 12 service boundary** — local-only programmatic query API, deterministic rebuild command, run manifest, artifact hashes и baseline drift checks.
12. **Stage 13 eval/tool adapter** — checked-in sanitized eval fixtures, multi-query eval suite и safe Hermes tool response wrapper.

## Установка

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

Runtime dependencies отсутствуют, кроме Python standard library. Для тестов используется `pytest`.

## Тесты

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Локальный gate на момент публикации:

```text
59 passed
```

## Использование

### Source manifest

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli manifest obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-manifest.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD)
```

Source manifests содержат только metadata: source IDs, source URIs, content hashes, authority class, epoch, timestamp.

### Chunk manifest

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli chunks obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-chunks.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD) \
  --max-chars 1200
```

Chunk manifests сериализуют metadata и clean/redacted previews. Raw chunk text не сериализуется в JSONL.

### Recall из chunk manifest

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

### Recall из sanitized index

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

Stage 12 добавляет local-only rebuild boundary для всех derived artifacts. `--timestamp` обязателен, чтобы reproducible rebuilds были byte-identical при неизменных inputs; `--output-dir` должен быть вне canonical vault.

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

Команда пишет:

- `obsidian-manifest.jsonl`
- `obsidian-chunks.jsonl`
- `obsidian-search-terms.jsonl`
- `obsidian-term-graph.jsonl`
- `obsidian-fact-candidates.jsonl`
- `run-manifest.json`

`run-manifest.json` содержит schema version, epoch, non-secret source label, параметры, record counts, artifact filenames, byte sizes и `sha256:` hashes. Raw note text туда не сериализуется.

### Programmatic query boundary

Stage 12 также добавляет local importable query boundary:

```python
from cybrocamp_memory.service import query_artifacts_json

packet = query_artifacts_json(
    index_path="data/obsidian-search-terms.jsonl",
    graph_path="data/obsidian-term-graph.jsonl",
    query="survival economics CyBroSwarm server subscriptions",
    timestamp="2026-04-29T00:00:00Z",
)
```

Это не daemon. Он не bind-ит ports, не вызывает network services и не пишет в canonical Obsidian/MemPalace. Он загружает derived artifacts и возвращает provenance-bearing recall packet.

### Stage 13 eval suite

Stage 13 добавляет checked-in sanitized synthetic fixtures в `tests/fixtures/stage13/` и multi-query regression gate:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli eval-suite \
  --index tests/fixtures/stage13/search_terms.jsonl \
  --graph tests/fixtures/stage13/term_graph.jsonl \
  --cases tests/fixtures/stage13/eval_cases.json \
  --output data/stage13-eval-report.json \
  --timestamp 2026-04-29T00:00:00Z \
  --top-k 5
```

Report хранит case IDs, pass/fail, expected source IDs, observed source IDs и drift/staleness failures. Raw vault text туда не пишется.

### Hermes tool adapter

Stage 13 также добавляет safe local Hermes-facing wrapper:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli hermes-query \
  --index data/obsidian-search-terms.jsonl \
  --graph data/obsidian-term-graph.jsonl \
  --query "survival economics CyBroSwarm server subscriptions" \
  --output data/hermes-query-survival-economics.json \
  --timestamp 2026-04-29T00:00:00Z
```

Wrapper возвращает `cybrocamp.hermes_tool_response.v1` с `canonical_writes=false`, `network_calls=false` и `requires_human_approval_for_promotion=true`.

## Authority model

Authority classes:

- `user_direct`
- `canonical_vault`
- `canonical_mempalace`
- `local_mempalace`
- `a2a_peer_claim`
- `cron_result`
- `derived_summary`
- `external_source`
- `payload_untrusted`

Только `user_direct` может поддерживать approval claims. Derived summaries, graph paths, co-occurrence facts, MemPalace comparison signals и A2A peer summaries не являются approval.

## Safety posture

CyBroCamp безопасен только как sidecar.

Его нельзя использовать как drop-in replacement для canonical memory или authorization. Graph подсказывает, куда смотреть; он не решает, что истинно.

Hard gates:

- no secret leakage;
- no permission promotion;
- no peer-claim promotion;
- stale evidence is blocked or flagged;
- derived artifacts stay outside canonical Obsidian/MemPalace;
- promotion to canonical memory requires explicit audit and approval.

## Repository hygiene

Generated artifacts намеренно ignored:

```text
data/**/*.jsonl
data/**/*.json
```

Не коммитить local vault exports, credentials, API keys, tokens, cookies, private keys или raw secret-bearing derived indexes.

## License

Лицензия пока не выбрана.
