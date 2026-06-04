"""
Phase 1 SQLite store — CRUD operations for sources, documents, chunks,
and memory_records.

Batch insert discipline: chunks and memory_records are inserted in
executemany() calls per document, not one-by-one in a loop.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from cerebra.storage.db import connect


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return connect(self._db_path)

    # ── Sources ───────────────────────────────────────────────────────────────

    def upsert_source(self, source: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sources (
                    source_id, canonical_path, content_hash, size_bytes,
                    detected_type, detection_confidence, parser_adapter,
                    parser_version, chunker_version, parser_status,
                    lifecycle_state, created_at, modified_at, ingested_at,
                    schema_version
                ) VALUES (
                    :source_id, :canonical_path, :content_hash, :size_bytes,
                    :detected_type, :detection_confidence, :parser_adapter,
                    :parser_version, :chunker_version, :parser_status,
                    :lifecycle_state, :created_at, :modified_at, :ingested_at,
                    :schema_version
                )
                ON CONFLICT(source_id) DO UPDATE SET
                    content_hash         = excluded.content_hash,
                    size_bytes           = excluded.size_bytes,
                    detected_type        = excluded.detected_type,
                    detection_confidence = excluded.detection_confidence,
                    parser_adapter       = excluded.parser_adapter,
                    parser_version       = excluded.parser_version,
                    chunker_version      = excluded.chunker_version,
                    parser_status        = excluded.parser_status,
                    lifecycle_state      = excluded.lifecycle_state,
                    modified_at          = excluded.modified_at,
                    ingested_at          = excluded.ingested_at
                """,
                source,
            )

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM sources WHERE source_id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def get_source_by_path(self, canonical_path: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sources WHERE canonical_path = ?", (canonical_path,)
            ).fetchone()
        return dict(row) if row else None

    def mark_source_stale(self, source_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sources SET lifecycle_state = 'stale' WHERE source_id = ?",
                (source_id,),
            )

    # ── Documents ─────────────────────────────────────────────────────────────

    def insert_document(self, doc: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, source_id, document_type, title,
                    artifact_path, normalization_confidence,
                    parse_warnings, lifecycle_state, created_at,
                    schema_version
                ) VALUES (
                    :document_id, :source_id, :document_type, :title,
                    :artifact_path, :normalization_confidence,
                    :parse_warnings, :lifecycle_state, :created_at,
                    :schema_version
                )
                """,
                doc,
            )

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_active_document_for_source(self, source_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE source_id = ? AND lifecycle_state = 'active'",
                (source_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_documents_stale_for_source(self, source_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET lifecycle_state = 'stale' WHERE source_id = ?",
                (source_id,),
            )

    # ── Chunks ────────────────────────────────────────────────────────────────

    def insert_chunks_batch(self, chunks: list[dict[str, Any]]) -> None:
        """Batch insert all chunks for a document in one executemany call."""
        if not chunks:
            return
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, source_id, heading_path,
                    chunk_index, depth, content, content_hash,
                    token_estimate, chunk_strategy, lifecycle_state,
                    created_at, schema_version
                ) VALUES (
                    :chunk_id, :document_id, :source_id, :heading_path,
                    :chunk_index, :depth, :content, :content_hash,
                    :token_estimate, :chunk_strategy, :lifecycle_state,
                    :created_at, :schema_version
                )
                """,
                chunks,
            )

    def get_chunks_for_document(self, document_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_chunks_stale_for_source(self, source_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE chunks SET lifecycle_state = 'stale' WHERE source_id = ?",
                (source_id,),
            )

    # ── Memory Records ────────────────────────────────────────────────────────

    def insert_records_batch(self, records: list[dict[str, Any]]) -> None:
        """Batch insert all memory records for a document in one executemany call."""
        if not records:
            return
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO memory_records (
                    record_id, record_type, source_id, document_id,
                    chunk_id, content, content_hash, token_estimate,
                    sku_address, sku_assigned_at, lifecycle_state,
                    created_at, schema_version
                ) VALUES (
                    :record_id, :record_type, :source_id, :document_id,
                    :chunk_id, :content, :content_hash, :token_estimate,
                    :sku_address, :sku_assigned_at, :lifecycle_state,
                    :created_at, :schema_version
                )
                """,
                records,
            )

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memory_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        return dict(row) if row else None

    def mark_records_stale_for_source(self, source_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE memory_records SET lifecycle_state = 'stale' WHERE source_id = ?",
                (source_id,),
            )

    def count_records_for_source(self, source_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE source_id = ? AND lifecycle_state = 'active'",
                (source_id,),
            ).fetchone()
        return row[0] if row else 0
