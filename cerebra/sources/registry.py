# SPDX-License-Identifier: Apache-2.0
"""
Source registry — registers files as sources, checks idempotency,
handles changed/stale lifecycle transitions.

Idempotency key: (canonical_path, content_hash, parser_version, chunker_version).
All four must match for a source to be skipped on re-ingest.

Source identity is canonical_path-based. A rename creates a new source;
the old one goes stale. Path-rename tracking is a Phase 3+ concern.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.sources.detector import DetectionResult
from cerebra.sources.hashing import hash_file, hash_string
from cerebra.storage.sqlite_store import SQLiteStore


def source_id_from_path(canonical_path: Path) -> str:
    """Stable source ID derived from canonical path (not content)."""
    return "src_" + hash_string(str(canonical_path))[:16]


class RegistrationOutcome(Enum):
    NEW = "new"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    CHANGED = "changed"


@dataclass
class SourceRecord:
    source_id: str
    canonical_path: str
    content_hash: str
    size_bytes: int
    detected_type: str
    detection_confidence: float
    parser_adapter: str | None
    parser_version: str | None
    chunker_version: str | None
    parser_status: str
    lifecycle_state: str
    created_at: int
    modified_at: int | None
    ingested_at: int | None
    schema_version: int

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "canonical_path": self.canonical_path,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "detected_type": self.detected_type,
            "detection_confidence": self.detection_confidence,
            "parser_adapter": self.parser_adapter,
            "parser_version": self.parser_version,
            "chunker_version": self.chunker_version,
            "parser_status": self.parser_status,
            "lifecycle_state": self.lifecycle_state,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "ingested_at": self.ingested_at,
            "schema_version": self.schema_version,
        }


def register_source(
    store: SQLiteStore,
    event_log: SQLiteEventLog,
    path: Path,
    detection: DetectionResult,
    parser_version: str | None,
    chunker_version: str | None,
) -> tuple[SourceRecord, RegistrationOutcome]:
    """
    Register a source file. Returns (record, outcome).

    Outcome determines whether the caller should proceed with parsing:
    - NEW: proceed
    - CHANGED: mark old data stale, proceed
    - SKIPPED_UNCHANGED: skip parsing entirely
    """
    now = int(time.time())
    content_hash = hash_file(path)
    size_bytes = path.stat().st_size
    sid = source_id_from_path(path)
    canonical = str(path)

    existing = store.get_source_by_path(canonical)

    if existing is not None:
        unchanged = (
            existing["content_hash"] == content_hash
            and existing["parser_version"] == parser_version
            and existing["chunker_version"] == chunker_version
            and existing["lifecycle_state"] == "active"
        )
        if unchanged:
            record = SourceRecord(
                source_id=existing["source_id"],
                canonical_path=canonical,
                content_hash=content_hash,
                size_bytes=size_bytes,
                detected_type=existing["detected_type"],
                detection_confidence=existing["detection_confidence"],
                parser_adapter=existing["parser_adapter"],
                parser_version=existing["parser_version"],
                chunker_version=existing["chunker_version"],
                parser_status=existing["parser_status"],
                lifecycle_state=existing["lifecycle_state"],
                created_at=existing["created_at"],
                modified_at=existing["modified_at"],
                ingested_at=existing["ingested_at"],
                schema_version=existing["schema_version"],
            )
            return record, RegistrationOutcome.SKIPPED_UNCHANGED

        # Content or version changed — mark everything stale
        store.mark_source_stale(sid)
        store.mark_documents_stale_for_source(sid)
        store.mark_chunks_stale_for_source(sid)
        store.mark_records_stale_for_source(sid)
        outcome = RegistrationOutcome.CHANGED
    else:
        outcome = RegistrationOutcome.NEW

    record = SourceRecord(
        source_id=sid,
        canonical_path=canonical,
        content_hash=content_hash,
        size_bytes=size_bytes,
        detected_type=detection.detected_type,
        detection_confidence=detection.confidence,
        parser_adapter=None,
        parser_version=parser_version,
        chunker_version=chunker_version,
        parser_status="pending",
        lifecycle_state="active",
        created_at=now,
        modified_at=None,
        ingested_at=None,
        schema_version=1,
    )
    store.upsert_source(record.as_dict())

    event_type = "SourceRegistered" if outcome == RegistrationOutcome.NEW else "SourceChanged"
    event_log.write(
        make_event(
            event_type=event_type,
            actor="source_registry",
            summary=f"{event_type}: {path.name}",
            data={
                "source_id": sid,
                "path": canonical,
                "content_hash": content_hash,
                "detected_type": detection.detected_type,
                "outcome": outcome.value,
            },
            subject_id=sid,
        )
    )

    return record, outcome
