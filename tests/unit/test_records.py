# SPDX-License-Identifier: Apache-2.0
"""Unit tests for memory record builder."""

from __future__ import annotations

import pytest

from cerebra.ingest.chunking import ChunkOptions, chunk_document
from cerebra.ingest.models import NormalizedDocument, Section
from cerebra.memory.records import build_record, build_records_for_document
from cerebra.sources.registry import SourceRecord


def _make_source() -> SourceRecord:
    return SourceRecord(
        source_id="src_test",
        canonical_path="/tmp/test.md",
        content_hash="abc123",
        size_bytes=100,
        detected_type="markdown",
        detection_confidence=0.95,
        parser_adapter="markdown",
        parser_version="1.0.0",
        chunker_version="1.0.0",
        parser_status="parsed",
        lifecycle_state="active",
        created_at=0,
        modified_at=None,
        ingested_at=None,
        schema_version=1,
    )


def _make_doc_with_one_chunk() -> tuple[NormalizedDocument, object]:
    section = Section(
        heading="Test",
        heading_path="Test",
        depth=1,
        content="Some content here.",
        start_line=0,
        end_line=1,
    )
    doc = NormalizedDocument(
        document_id="doc_test",
        source_id="src_test",
        document_type="markdown",
        title="Test",
        sections=[section],
        raw_content="Some content here.",
    )
    chunks = chunk_document(doc, ChunkOptions(max_tokens=100))
    return doc, chunks


@pytest.mark.unit
class TestMemoryRecordBuilder:
    def test_record_id_has_rec_prefix(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        record = build_record(chunks[0], source)
        assert record.record_id.startswith("rec_")

    def test_sku_address_is_none(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        record = build_record(chunks[0], source)
        assert record.sku_address is None
        assert record.sku_assigned_at is None

    def test_lifecycle_state_is_active(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        record = build_record(chunks[0], source)
        assert record.lifecycle_state == "active"

    def test_record_type_is_source_chunk(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        record = build_record(chunks[0], source)
        assert record.record_type == "source_chunk"

    def test_content_matches_chunk(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        record = build_record(chunks[0], source)
        assert record.content == chunks[0].content

    def test_build_records_for_document_one_per_chunk(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        records = build_records_for_document(chunks, source)
        assert len(records) == len(chunks)

    def test_as_dict_has_required_keys(self) -> None:
        _, chunks = _make_doc_with_one_chunk()
        source = _make_source()
        d = build_record(chunks[0], source).as_dict()
        required = {
            "record_id",
            "record_type",
            "source_id",
            "document_id",
            "chunk_id",
            "content",
            "content_hash",
            "token_estimate",
            "sku_address",
            "sku_assigned_at",
            "lifecycle_state",
            "created_at",
            "schema_version",
        }
        assert required.issubset(d.keys())
