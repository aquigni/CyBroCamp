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

The generated JSONL manifest is a derived local artifact and is intentionally ignored by git. It contains stable source IDs, content hashes, authority class, epoch, timestamp, and source URIs — not note contents.
