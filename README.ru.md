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
13. **Stage 14 promotion audit** — side-effect-free candidate review reports с evidence bundles, contradiction/staleness summaries и явными H0st approval gates.
14. **Stage 15 promotion plan** — approval-gated dry-run promotion plans, создающие non-writing operations только для exact H0st-approved candidates.
15. **Stage 16 locked preview** — второй locked review harness поверх Stage 15 plans, всё ещё без canonical writes.
16. **Stage 17 controlled execution receipt** — double-approved local receipts для reviewed operations; canonical network writes не выполняются.
17. **Stage 18 cortex rollout** — rollout трёх сестёр и auto-enrollment policy для будущих сестёр с least-privilege rights.
18. **Operational persistence bundle** — user-systemd timer и безопасный rebuild runner для постоянных derived cortex artifacts вне `/opt/obs/vault`.

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
119 passed
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

### Stage 14 promotion audit

Stage 14 добавляет no-write promotion audit report для проверки fact candidates до любого canonical memory action:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-audit \
  --facts data/obsidian-fact-candidates.jsonl \
  --output data/stage14-promotion-audit.json \
  --timestamp 2026-04-29T00:00:00Z
```

Опциональные `--current-source-hashes`, `--current-chunk-hashes` и `--mempalace-comparison` добавляют freshness checks и metadata-only MemPalace comparison. Report пишет `cybrocamp.promotion_audit.v1`, держит `canonical_writes=false`, включает evidence bundles с source/chunk hashes и UTF-8 byte spans, суммирует local contradictions, запрещает output внутри canonical vault и помечает каждый candidate как требующий explicit H0st approval before promotion.

### Stage 15 promotion plan

Stage 15 превращает Stage 14 audit report в deterministic dry-run plan. Без explicit approval-scope файла plan создаёт ноль operations:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-plan \
  --audit data/stage14-promotion-audit.json \
  --output data/stage15-promotion-plan.json \
  --timestamp 2026-04-29T00:00:00Z
```

С approval-scope JSON схемы `cybrocamp.approval_scope.v1` только exact `(candidate_id, action)` match, approved by `H0st`, может создать dry-run operation:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-plan \
  --audit data/stage14-promotion-audit.json \
  --approval-scope data/stage15-approval-scope.json \
  --output data/stage15-promotion-plan.json \
  --timestamp 2026-04-29T00:00:00Z
```

Plan пишет `cybrocamp.promotion_plan.v1` с `mode="dry_run"`, `canonical_writes=false`, `network_calls=false`, `would_write=false` для всех generated ops, sanitized candidate summaries, deterministic IDs/hashes и запретом output внутри `/opt/obs/vault`. Blocked audit items никогда не становятся operations, даже если approval-scope file их называет.

### Stage 16 locked preview

Stage 16 превращает Stage 15 plan в locked preview packet. Это review harness, не writer: без `cybrocamp.preview_lock.v1` файла от `H0st` preview writes остаются blocked.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-preview \
  --plan data/stage15-promotion-plan.json \
  --output data/stage16-locked-preview.json \
  --timestamp 2026-04-29T00:00:00Z
```

Matching lock scope может разблокировать preview rows только для inspection. `canonical_writes=false`, `network_calls=false`, `would_write=false` и `requires_second_h0st_approval_for_execution=true` сохраняются.

### Stage 17 controlled execution receipt

Stage 17 принимает locked preview и опциональный второй explicit execution approval схемы `cybrocamp.execution_approval.v1`. Команда пишет только local receipt; она не вызывает MemPalace, Obsidian, KG APIs или network services.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli promotion-execute \
  --preview data/stage16-locked-preview.json \
  --output data/stage17-execution-receipt.json \
  --timestamp 2026-04-29T00:00:00Z
```

Даже когда execution approval совпадает с preview hash и operation IDs, sink остаётся `local_receipt_only`, а `canonical_network_write_performed=false`. Receipt — auditable bridge к будущему canonical writer, но не сам writer.

### Stage 18 cortex rollout

Stage 18 выпускает sister-cortex rollout policy для Chthonya, Mac0sh, Debi0 и будущих сестёр. Он моделирует least-privilege rights, authority каждого node и auto-enrollment default.

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli cortex-rollout \
  --output data/stage18-cortex-rollout.json \
  --timestamp 2026-04-29T00:00:00Z
```

Будущие сёстры автоматически входят как `quarantined_readonly_until_explicit_approval`. Они могут делать bounded recall queries, но не могут строить canonical indexes, preview/execute promotions, писать canonical MemPalace, мутировать services или выдавать H0st approval.

### Operational persistence bundle

Persistence bundle создаёт installable user-systemd units для периодического rebuild derived cortex artifacts. Это всё ещё sidecar: артефакты пишутся под non-vault artifact root, runner вызывает только локальные CLI-команды, а generated safety envelope фиксирует `canonical_writes=false`, `network_calls=false`, `approval_state_writes=false` и `writes_inside_vault=false`.

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

Целевой installation layer — user systemd: `~/.local/bin/` и `~/.config/systemd/user/`. Timer использует `Persistent=true`, `OnBootSec=2min` и `OnUnitActiveSec=<N>min`.

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
