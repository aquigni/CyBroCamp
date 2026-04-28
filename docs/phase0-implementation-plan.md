# CyBroCamp Memory Sidecar Phase 0/1 Implementation Plan

> **For Hermes:** Use test-driven-development for every code-bearing task.

**Goal:** build the first safe obvjazka for the sister hippocampal/cortical layer: schema, source manifest, evidence spans, and RecallPacket policy gates.

**Architecture:** authority remains in Obsidian/MemPalace/A2A logs. This project produces derived recall artifacts only. Retrieval and graph expansion may suggest evidence; they cannot grant facthood or approval.

**Tech Stack:** Python 3.11, dataclasses, SQLite/FTS5 in the next slice, NetworkX/PPR later if evaluation justifies it.

## Slice 0 — completed scaffold

- `AuthorityClass`
- `EvidenceSpan`
- `RecallItem`
- `RecallPacket`
- first safety gate: non-`user_direct` approval claims are flagged as `non_user_direct_approval_claim`
- tests under `tests/test_schema.py`

## Next Slice 1 — source manifest

1. Add `SourceRecord` schema with:
   - `source_id`
   - `uri`
   - `authority`
   - `epoch`
   - `content_hash`
   - `created_at`
2. Add content hashing helper for markdown/log chunks.
3. Add read-only Obsidian adapter for selected markdown files.
4. Add manifest JSONL writer under local sidecar data dir.
5. Gate: no adapter may write to `/opt/obs/vault` or MemPalace.

## Next Slice 2 — OpenZiti obvjazka plan

OpenZiti is tracked as network substrate hardening, not part of memory authority. First implementation action should be read-only/environment design:

1. inventory current access paths and ports;
2. decide controller placement;
3. define identities for Chthonya, Mac0sh, future cortical nodes, and admin operator;
4. prototype a private service for a non-critical endpoint;
5. only after explicit approval: install controller/edge router/tunneler.
