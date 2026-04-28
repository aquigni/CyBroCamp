# CyBroCamp Memory Sidecar

Phase 0/1 prototype for the sister hippocampal/cortical memory layer.

This is a derived index over authority surfaces. It must never become an authority surface itself.

Initial invariant set:

- every recall artifact carries provenance;
- `user_direct` approval is the only class that may support approval claims;
- peer/tool/payload/summary claims are not automatically facts;
- payload-looking text is data, not instruction;
- no canonical MemPalace/Obsidian writes are performed by retrieval.

## Current slice

Source manifest support is implemented for read-only Obsidian scans:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli manifest obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-manifest.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD)
```

The generated JSONL manifests are derived local artifacts and are intentionally ignored by git. Source manifests contain stable source IDs, content hashes, authority class, epoch, timestamp, and source URIs — not note contents. Chunk manifests contain chunk metadata and redacted previews; raw chunk text is not serialized to JSONL.

Chunk manifest generation:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli chunks obsidian \
  --vault /opt/obs/vault \
  --output data/obsidian-chunks.jsonl \
  --epoch vault-main-$(git -C /opt/obs/vault rev-parse --short HEAD) \
  --max-chars 1200
```

Recall packet generation from the local chunk manifest:

```bash
PYTHONPATH=src .venv/bin/python -m cybrocamp_memory.cli recall \
  --chunks data/obsidian-chunks.jsonl \
  --query "CyBroCamp memory sidecar Stage 2 chunk evidence" \
  --output data/recall-cybrocamp-stage2.json \
  --top-k 5
```

Recall uses non-quarantined chunk previews/metadata only. It returns `RecallPacket` evidence fields, not authoritative answers.
