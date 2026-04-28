from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

from .manifest import SourceRecord, compute_content_hash, manifest_records_from_obsidian
from .schema import AuthorityClass, EvidenceSpan, RecallItem


CHUNK_SCHEMA_VERSION = "cybrocamp.chunk_record.v1"

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret", re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|cookie)\s*[:=]\s*\S+")),
    ("secret", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    ("secret", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret", re.compile(r"\b(?:sk|ghp|xox[baprs])-[-A-Za-z0-9_]{8,}\b")),
    ("secret", re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")),
)

_PAYLOAD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("payload_instruction", re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions")),
    ("payload_instruction", re.compile(r"(?i)\b(system|developer|assistant)\s*prompt\b")),
    ("payload_instruction", re.compile(r"(?i)<script\b")),
    ("payload_instruction", re.compile(r"(?i)\btool_calls?\b|\bfunction_call\b")),
)


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    source_id: str
    source_uri: str
    chunk_id: str
    chunk_index: int
    content_hash: str
    source_content_hash: str
    span_start: int
    span_end: int
    text: str
    text_preview: str
    authority: AuthorityClass
    quarantine_flags: list[str]
    schema_version: str = CHUNK_SCHEMA_VERSION

    @classmethod
    def from_text(
        cls,
        source: SourceRecord,
        chunk_index: int,
        text: str,
        span_start: int,
        span_end: int,
    ) -> "ChunkRecord":
        content_hash = compute_content_hash(text)
        flags = quarantine_flags_for_text(text)
        return cls(
            source_id=source.source_id,
            source_uri=source.uri,
            chunk_id=compute_content_hash(f"{source.source_id}:{chunk_index}:{content_hash}"),
            chunk_index=chunk_index,
            content_hash=content_hash,
            source_content_hash=source.content_hash,
            span_start=span_start,
            span_end=span_end,
            text=text,
            text_preview=_preview(text, flags),
            authority=source.authority,
            quarantine_flags=flags,
        )

    def to_json_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["authority"] = self.authority.value
        data.pop("text", None)
        return data

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> "ChunkRecord":
        return cls(
            source_id=str(data["source_id"]),
            source_uri=str(data["source_uri"]),
            chunk_id=str(data["chunk_id"]),
            chunk_index=int(data["chunk_index"]),
            content_hash=str(data["content_hash"]),
            source_content_hash=str(data["source_content_hash"]),
            span_start=int(data["span_start"]),
            span_end=int(data["span_end"]),
            text=str(data.get("text", data.get("text_preview", ""))),
            text_preview=str(data["text_preview"]),
            authority=AuthorityClass(str(data["authority"])),
            quarantine_flags=[str(flag) for flag in data.get("quarantine_flags", [])],
            schema_version=str(data.get("schema_version", CHUNK_SCHEMA_VERSION)),
        )

    def to_evidence_span(self) -> EvidenceSpan:
        return EvidenceSpan(
            source_uri=self.source_uri,
            start=self.span_start,
            end=self.span_end,
            content_hash=self.content_hash,
            source_id=self.source_id,
            chunk_id=self.chunk_id,
            authority=self.authority,
            quarantine_flags=list(self.quarantine_flags),
            source_content_hash=self.source_content_hash,
            stale_flags=[],
        )


def chunk_text(source: SourceRecord, text: str, *, max_chars: int = 1200) -> list[ChunkRecord]:
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    spans = _combined_paragraph_spans(text, max_chars)
    chunks: list[ChunkRecord] = []
    for start_char, end_char in spans:
        for part_start, part_end in _split_span(text, start_char, end_char, max_chars):
            raw = text[part_start:part_end]
            if raw == "":
                continue
            chunks.append(
                ChunkRecord.from_text(
                    source,
                    len(chunks),
                    raw,
                    _byte_offset(text, part_start),
                    _byte_offset(text, part_end),
                )
            )
    if not chunks and text == "":
        chunks.append(ChunkRecord.from_text(source, 0, "", 0, 0))
    return chunks


def chunk_records_from_obsidian(
    vault_root: str | Path,
    *,
    max_chars: int = 1200,
    epoch: str = "obsidian-scan-v1",
    created_at: str = "1970-01-01T00:00:00Z",
) -> Iterator[ChunkRecord]:
    vault = Path(vault_root).resolve(strict=True)
    for source in manifest_records_from_obsidian(vault, epoch=epoch, created_at=created_at):
        path = _obsidian_uri_to_path(vault, source.uri)
        text = path.read_text(encoding="utf-8")
        yield from chunk_text(source, text, max_chars=max_chars)


def write_chunk_manifest_jsonl(path: str | Path, records: Iterable[ChunkRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    unique = {record.chunk_id: record for record in records}
    ordered = [unique[key] for key in sorted(unique)]
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in ordered:
                json.dump(record.to_json_dict(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_chunk_manifest_jsonl(path: str | Path) -> list[ChunkRecord]:
    records: list[ChunkRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            data = json.loads(line)
            try:
                records.append(ChunkRecord.from_json_dict(data))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid chunk manifest line {line_number}") from exc
    return records


def chunks_to_recall_items(chunks: Sequence[ChunkRecord], *, timestamp: str) -> list[RecallItem]:
    return [
        RecallItem(
            text=chunk.text_preview,
            authority=chunk.authority,
            evidence=chunk.to_evidence_span(),
            timestamp=timestamp,
        )
        for chunk in chunks
    ]


def embed_allowed_chunks(
    chunks: Sequence[ChunkRecord],
    embedder: Callable[[list[str]], Sequence[object]],
) -> dict[str, object]:
    allowed = [chunk for chunk in chunks if not chunk.quarantine_flags]
    embeddings = embedder([chunk.text for chunk in allowed]) if allowed else []
    return {chunk.chunk_id: embedding for chunk, embedding in zip(allowed, embeddings, strict=True)}


def quarantine_flags_for_text(text: str) -> list[str]:
    flags: list[str] = []
    for flag, pattern in (*_SECRET_PATTERNS, *_PAYLOAD_PATTERNS):
        if pattern.search(text) and flag not in flags:
            flags.append(flag)
    return sorted(flags)


def _combined_paragraph_spans(text: str, max_chars: int) -> list[tuple[int, int]]:
    paragraphs = _paragraph_spans(text)
    if not paragraphs:
        return []
    combined: list[tuple[int, int]] = []
    start, end = paragraphs[0]
    for next_start, next_end in paragraphs[1:]:
        if next_end - start <= max_chars:
            end = next_end
        else:
            combined.append((start, end))
            start, end = next_start, next_end
    combined.append((start, end))
    return combined


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    if text == "":
        return []
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in re.finditer(r"\n\s*\n", text):
        end = match.start()
        if end > pos:
            spans.append((pos, end))
        pos = match.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return spans


def _split_span(text: str, start: int, end: int, max_chars: int) -> Iterator[tuple[int, int]]:
    cursor = start
    while cursor < end:
        yield cursor, min(cursor + max_chars, end)
        cursor += max_chars


def _byte_offset(text: str, char_index: int) -> int:
    return len(text[:char_index].encode("utf-8"))


def _preview(text: str, flags: Sequence[str]) -> str:
    if flags:
        return "[REDACTED:" + ",".join(flags) + "]"
    return " ".join(text.split())[:200]


def _obsidian_uri_to_path(vault: Path, uri: str) -> Path:
    if not uri.startswith("obsidian://"):
        raise ValueError(f"unsupported source uri: {uri}")
    rel = uri.removeprefix("obsidian://")
    path = (vault / rel).resolve(strict=True)
    try:
        path.relative_to(vault)
    except ValueError as exc:
        raise ValueError(f"source path is outside vault: {path}") from exc
    return path
