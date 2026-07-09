# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SQLiteStore CRUD operations."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cerebra.storage.migrations import run_migrations
from cerebra.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    db = tmp_path / "test.db"
    run_migrations(db)
    return SQLiteStore(db)


def _source(path: str = "/tmp/doc.md") -> dict:
    return {
        "source_id": "src_abc",
        "canonical_path": path,
        "content_hash": "hash1",
        "size_bytes": 100,
        "detected_type": "markdown",
        "detection_confidence": 0.95,
        "parser_adapter": "markdown",
        "parser_version": "1.0.0",
        "chunker_version": "1.0.0",
        "parser_status": "parsed",
        "lifecycle_state": "active",
        "created_at": int(time.time()),
        "modified_at": None,
        "ingested_at": int(time.time()),
        "schema_version": 1,
    }


def _doc(source_id: str = "src_abc") -> dict:
    return {
        "document_id": "doc_abc",
        "source_id": source_id,
        "document_type": "markdown",
        "title": "Test",
        "artifact_path": "/tmp/artifact.json",
        "normalization_confidence": 0.9,
        "parse_warnings": None,
        "lifecycle_state": "active",
        "created_at": int(time.time()),
        "schema_version": 1,
    }


def _chunk(doc_id: str = "doc_abc", source_id: str = "src_abc", idx: int = 0) -> dict:
    return {
        "chunk_id": f"chk_{idx:04d}",
        "document_id": doc_id,
        "source_id": source_id,
        "heading_path": "Section",
        "chunk_index": idx,
        "depth": 1,
        "content": f"Content {idx}",
        "content_hash": f"hash_chunk_{idx}",
        "token_estimate": 10,
        "chunk_strategy": "heading",
        "lifecycle_state": "active",
        "created_at": int(time.time()),
        "schema_version": 1,
    }


def _record(
    source_id: str = "src_abc", doc_id: str = "doc_abc", chunk_id: str = "chk_0000"
) -> dict:
    return {
        "record_id": f"rec_{chunk_id}",
        "record_type": "source_chunk",
        "source_id": source_id,
        "document_id": doc_id,
        "chunk_id": chunk_id,
        "content": "Content",
        "content_hash": "hash_rec",
        "token_estimate": 10,
        "sku_address": None,
        "sku_assigned_at": None,
        "lifecycle_state": "active",
        "created_at": int(time.time()),
        "schema_version": 1,
    }


@pytest.mark.unit
class TestSQLiteStore:
    def test_upsert_and_get_source(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        got = store.get_source("src_abc")
        assert got is not None
        assert got["source_id"] == "src_abc"

    def test_get_source_by_path(self, store: SQLiteStore) -> None:
        store.upsert_source(_source("/tmp/doc.md"))
        got = store.get_source_by_path("/tmp/doc.md")
        assert got is not None

    def test_get_source_returns_none_for_missing(self, store: SQLiteStore) -> None:
        assert store.get_source("nonexistent") is None

    def test_mark_source_stale(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.mark_source_stale("src_abc")
        got = store.get_source("src_abc")
        assert got["lifecycle_state"] == "stale"

    def test_insert_and_get_document(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        got = store.get_document("doc_abc")
        assert got is not None
        assert got["title"] == "Test"

    def test_get_active_document_for_source(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        got = store.get_active_document_for_source("src_abc")
        assert got is not None

    def test_mark_documents_stale(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        store.mark_documents_stale_for_source("src_abc")
        got = store.get_active_document_for_source("src_abc")
        assert got is None  # none active

    def test_batch_insert_and_get_chunks(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        chunks = [_chunk(idx=i) for i in range(5)]
        store.insert_chunks_batch(chunks)
        got = store.get_chunks_for_document("doc_abc")
        assert len(got) == 5

    def test_mark_chunks_stale(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        store.insert_chunks_batch([_chunk(idx=0)])
        store.mark_chunks_stale_for_source("src_abc")
        chunks = store.get_chunks_for_document("doc_abc")
        assert all(c["lifecycle_state"] == "stale" for c in chunks)

    def test_batch_insert_records(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        store.insert_chunks_batch([_chunk(idx=0)])
        store.insert_records_batch([_record()])
        assert store.count_records_for_source("src_abc") == 1

    def test_mark_records_stale(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        store.insert_chunks_batch([_chunk(idx=0)])
        store.insert_records_batch([_record()])
        store.mark_records_stale_for_source("src_abc")
        assert store.count_records_for_source("src_abc") == 0

    def test_get_record(self, store: SQLiteStore) -> None:
        store.upsert_source(_source())
        store.insert_document(_doc())
        store.insert_chunks_batch([_chunk(idx=0)])
        store.insert_records_batch([_record()])
        r = store.get_record("rec_chk_0000")
        assert r is not None
        assert r["record_type"] == "source_chunk"
