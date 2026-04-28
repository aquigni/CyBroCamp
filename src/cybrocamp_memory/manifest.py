from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .schema import AuthorityClass


HASH_ALGORITHM = "sha256"
MANIFEST_SCHEMA_VERSION = "cybrocamp.source_record.v1"


def compute_content_hash(content: str | bytes) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return f"{HASH_ALGORITHM}:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_id: str
    uri: str
    authority: AuthorityClass
    epoch: str
    content_hash: str
    created_at: str
    schema_version: str = MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_obsidian_note(
        cls,
        vault_root: str | Path,
        note_path: str | Path,
        *,
        epoch: str = "obsidian-scan-v1",
        created_at: str = "1970-01-01T00:00:00Z",
        authority: AuthorityClass = AuthorityClass.CANONICAL_VAULT,
    ) -> "SourceRecord":
        vault = Path(vault_root).resolve(strict=True)
        note = Path(note_path).resolve(strict=True)
        _ensure_inside(vault, note)
        if note.suffix.lower() != ".md":
            raise ValueError("obsidian source must be a markdown note")
        rel = note.relative_to(vault).as_posix()
        if rel.startswith(".obsidian/"):
            raise ValueError("obsidian internal files are not source notes")
        content = note.read_bytes()
        uri = f"obsidian://{rel}"
        return cls(
            source_id=compute_content_hash(f"obsidian:{rel}"),
            uri=uri,
            authority=authority,
            epoch=epoch,
            content_hash=compute_content_hash(content),
            created_at=created_at,
        )

    def to_json_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["authority"] = self.authority.value
        return data


def manifest_records_from_obsidian(
    vault_root: str | Path,
    *,
    epoch: str = "obsidian-scan-v1",
    created_at: str = "1970-01-01T00:00:00Z",
) -> Iterator[SourceRecord]:
    vault = Path(vault_root).resolve(strict=True)
    for path in sorted(vault.rglob("*.md")):
        if _is_hidden_or_obsidian_internal(vault, path):
            continue
        yield SourceRecord.from_obsidian_note(
            vault,
            path,
            epoch=epoch,
            created_at=created_at,
        )


def write_manifest_jsonl(path: str | Path, records: Iterable[SourceRecord]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    unique = {(_dedupe_key(record)): record for record in records}
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


def _dedupe_key(record: SourceRecord) -> tuple[str, str, str]:
    return (record.source_id, record.content_hash, record.epoch)


def _ensure_inside(root: Path, path: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"source path is outside vault: {path}") from exc


def _is_hidden_or_obsidian_internal(vault: Path, path: Path) -> bool:
    rel_parts = path.resolve(strict=True).relative_to(vault).parts
    return any(part.startswith(".") for part in rel_parts)
