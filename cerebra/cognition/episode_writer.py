"""Phase 8 v0.3.5a — EpisodeWriter: cycle episode persistence.

Phase 10: EpisodeWriter now dual-writes to both cycle_episode_records (primary,
for direct session queries) and memory_records (record_type='cycle_episode',
for retrieval visibility). The memory_records write uses synthetic sentinel FKs
inserted by Migration018. Embeddings are queued after each write so the vector
index picks up cycle output.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cerebra.cognition._constants import (
    SYNTHETIC_CHUNK_ID,
    SYNTHETIC_DOCUMENT_ID,
    SYNTHETIC_SOURCE_ID,
)
from cerebra.storage.embeddings import queue_for_embedding

# ── helpers ───────────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_record_id() -> str:
    return f"ep_{uuid.uuid4().hex[:12]}"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── EpisodeRecord dataclass ───────────────────────────────────────────────────


@dataclass(frozen=True)
class EpisodeRecord:
    """Immutable view of a persisted cycle episode record."""

    record_id: str
    runtime_session_id: str
    cycle_id: str
    step_id: str
    step_name: str
    content: str
    created_at: int
    working_memory_session_id: str | None = None
    content_summary: str | None = None
    metadata: dict[str, Any] | None = None
    leeway_grant_event_id: bytes | None = None
    cited_record_ids: list[str] | None = None


# ── EpisodeWriter ─────────────────────────────────────────────────────────────


class EpisodeWriter:
    """Writes and reads cycle-generated episode records.

    Placement in cognition/ reflects that episodes are cycle-derived (cognitive
    artefacts), not ingestion-derived (storage artefacts). CycleRuntime is the
    primary consumer.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def write(
        self,
        content: str,
        runtime_session_id: str,
        cycle_id: str,
        step_id: str,
        step_name: str,
        working_memory_session_id: str | None = None,
        leeway_grant_event_id: bytes | None = None,
        cited_record_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a cycle episode record. Returns the generated record_id."""
        record_id = _generate_record_id()
        content_summary = content[:200] if len(content) > 200 else content
        cited_json = json.dumps(cited_record_ids or [])
        metadata_json = json.dumps(metadata or {})

        now = _now_ms()
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        token_estimate = len(content.split())

        with _connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO cycle_episode_records (
                    record_id, runtime_session_id, working_memory_session_id,
                    cycle_id, step_id, step_name, content, content_summary,
                    metadata, leeway_grant_event_id, cited_record_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    runtime_session_id,
                    working_memory_session_id,
                    cycle_id,
                    step_id,
                    step_name,
                    content,
                    content_summary,
                    metadata_json,
                    leeway_grant_event_id,
                    cited_json,
                    now,
                ),
            )
            # Phase 10 bridge: dual-write to memory_records so cycle output is
            # visible to the retrieval pipeline. Sentinel FKs from Migration018.
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_records (
                    record_id, record_type, source_id, document_id, chunk_id,
                    content, content_hash, token_estimate, lifecycle_state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    "cycle_episode",
                    SYNTHETIC_SOURCE_ID,
                    SYNTHETIC_DOCUMENT_ID,
                    SYNTHETIC_CHUNK_ID,
                    content,
                    content_hash,
                    token_estimate,
                    "active",
                    now,
                ),
            )

        # Queue for vector embedding outside the transaction (best-effort).
        queue_for_embedding(self.db_path, [record_id])

        return record_id

    def read(self, record_id: str) -> EpisodeRecord | None:
        """Read an episode by record_id. Returns None if not found."""
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM cycle_episode_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def list_for_runtime_session(self, runtime_session_id: str) -> list[EpisodeRecord]:
        """List all episodes for a runtime session, ordered by created_at ASC."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM cycle_episode_records "
                "WHERE runtime_session_id = ? ORDER BY created_at ASC",
                (runtime_session_id,),
            ).fetchall()
        return [_row_to_record(r) for r in rows]


# ── Row deserializer ──────────────────────────────────────────────────────────


def _row_to_record(row: sqlite3.Row) -> EpisodeRecord:
    cited_raw = row["cited_record_ids"]
    cited: list[str] | None = json.loads(cited_raw) if cited_raw else None
    meta_raw = row["metadata"]
    meta: dict[str, Any] | None = json.loads(meta_raw) if meta_raw else None
    return EpisodeRecord(
        record_id=row["record_id"],
        runtime_session_id=row["runtime_session_id"],
        working_memory_session_id=row["working_memory_session_id"],
        cycle_id=row["cycle_id"],
        step_id=row["step_id"],
        step_name=row["step_name"],
        content=row["content"],
        content_summary=row["content_summary"],
        metadata=meta,
        leeway_grant_event_id=row["leeway_grant_event_id"],
        cited_record_ids=cited,
        created_at=row["created_at"],
    )
