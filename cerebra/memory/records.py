# SPDX-License-Identifier: Apache-2.0
"""
Memory record builder — converts chunks into memory_records rows.

Every record starts with sku_address=None. Phase 2 fills SKU addresses
by running the classifier over all records where sku_address IS NULL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from cerebra.ingest.chunking import Chunk
from cerebra.sources.hashing import hash_string
from cerebra.sources.registry import SourceRecord


@dataclass
class MemoryRecord:
    record_id: str
    record_type: str  # "source_chunk" in Phase 1
    source_id: str
    document_id: str
    chunk_id: str
    content: str
    content_hash: str
    token_estimate: int
    sku_address: str | None  # None until Phase 2
    sku_assigned_at: int | None
    lifecycle_state: str
    created_at: int
    schema_version: int

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "source_id": self.source_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "token_estimate": self.token_estimate,
            "sku_address": self.sku_address,
            "sku_assigned_at": self.sku_assigned_at,
            "lifecycle_state": self.lifecycle_state,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }


def build_record(chunk: Chunk, source: SourceRecord) -> MemoryRecord:
    """Build a MemoryRecord from a Chunk. SKU address is always None here."""
    record_id = "rec_" + hash_string(chunk.chunk_id)[:12]
    return MemoryRecord(
        record_id=record_id,
        record_type="source_chunk",
        source_id=source.source_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        content=chunk.content,
        content_hash=chunk.content_hash,
        token_estimate=chunk.token_estimate,
        sku_address=None,
        sku_assigned_at=None,
        lifecycle_state="active",
        created_at=int(time.time()),
        schema_version=1,
    )


def build_records_for_document(
    chunks: list[Chunk],
    source: SourceRecord,
) -> list[MemoryRecord]:
    """Build all MemoryRecords for a document's chunks."""
    return [build_record(chunk, source) for chunk in chunks]
