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

    # ── SKU assignments ───────────────────────────────────────────────────────

    def insert_sku_assignment(self, assignment: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sku_assignments (
                    assignment_id, record_id, sku_address,
                    d1, d2, d3, d4, d5, d6, d7, d8, d9, d10,
                    raw_scores_json, d1_confidence,
                    classifier_version, prompt_version,
                    subcategory_strategy_version,
                    model_string, latency_ms, input_tokens, output_tokens,
                    pass_count, created_at, schema_version
                ) VALUES (
                    :assignment_id, :record_id, :sku_address,
                    :d1, :d2, :d3, :d4, :d5, :d6, :d7, :d8, :d9, :d10,
                    :raw_scores_json, :d1_confidence,
                    :classifier_version, :prompt_version,
                    :subcategory_strategy_version,
                    :model_string, :latency_ms, :input_tokens, :output_tokens,
                    :pass_count, :created_at, :schema_version
                )
                """,
                assignment,
            )

    def get_sku_assignment_for_record(self, record_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sku_assignments WHERE record_id = ? ORDER BY created_at DESC LIMIT 1",
                (record_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_sku_assignment_for_record(self, record_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM sku_assignments WHERE record_id = ?",
                (record_id,),
            )

    def update_record_sku(self, record_id: str, sku_address: str, assigned_at: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE memory_records SET sku_address = ?, sku_assigned_at = ? WHERE record_id = ?",
                (sku_address, assigned_at, record_id),
            )

    def count_sku_location_occupancy(
        self, d1: int, d2: int, d3: int, d4: int, d5: int, d6: int, d9: int, d10: int
    ) -> int:
        """Count existing sku_assignments at the full location tuple for D7-D8 derivation."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM sku_assignments
                WHERE d1=? AND d2=? AND d3=? AND d4=? AND d5=? AND d6=? AND d9=? AND d10=?
                """,
                (d1, d2, d3, d4, d5, d6, d9, d10),
            ).fetchone()
        return row[0] if row else 0

    def get_records_needing_classification(
        self, classifier_version: str, prompt_version: str
    ) -> list[dict[str, Any]]:
        """
        Return all memory records that need SKU classification:
        - sku_address IS NULL (never classified), OR
        - existing assignment has mismatched classifier_version or prompt_version
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT mr.record_id, mr.content, s.detected_type
                FROM memory_records mr
                LEFT JOIN sources s ON mr.source_id = s.source_id
                LEFT JOIN sku_assignments sa ON mr.record_id = sa.record_id
                WHERE mr.lifecycle_state = 'active'
                  AND (
                    mr.sku_address IS NULL
                    OR sa.classifier_version != ?
                    OR sa.prompt_version != ?
                  )
                """,
                (classifier_version, prompt_version),
            ).fetchall()
        return [dict(row) for row in rows]
