# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the six-step SKU traversal (cerebra/retrieval/traversal.py)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cerebra.retrieval.planner import QueryPlan
from cerebra.retrieval.traversal import (
    RawCandidate,
    _assemble_retrieval_path,
    _step1_construct_sku_query,
    _step2_exact_sku,
    _step3_partial_sku,
    run_traversal,
    traverse_siblings,
)
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _migrated_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    run_migrations(db)
    return db


def _plan(
    query: str,
    *,
    mode: str = "hybrid",
    query_d1: int | None = None,
    max_candidates: int = 200,
) -> QueryPlan:
    """Create a minimal QueryPlan for testing traversal in isolation."""
    return QueryPlan(
        trace_id="trace_test0000001",
        raw_query=query,
        query_d1=query_d1,
        query_d1_d2_d3=f"0x{query_d1:x}" if query_d1 is not None else None,
        mode=mode,
        max_candidates=max_candidates,
        staleness_warnings=[],
    )


_SHARED_SOURCE_ID = "src_test_shared"
_SHARED_DOC_ID = "doc_test_shared"
_SHARED_CHUNK_PREFIX = "chk_test_"


def _ensure_source_doc(conn: sqlite3.Connection) -> None:
    """Insert shared source + document rows (idempotent via INSERT OR IGNORE)."""
    import time as _time

    now = int(_time.time())
    conn.execute(
        "INSERT OR IGNORE INTO sources "
        "(source_id, canonical_path, content_hash, size_bytes, detected_type, "
        " detection_confidence, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
        (_SHARED_SOURCE_ID, "/test/fixture.md", "hash_src", 100, "markdown", 1.0, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO documents "
        "(document_id, source_id, document_type, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, 'active', ?)",
        (_SHARED_DOC_ID, _SHARED_SOURCE_ID, "markdown", now),
    )


def _insert_sku_record(conn: sqlite3.Connection, record_id: str, d1: int) -> None:
    """Insert the full FK chain: source + doc + chunk + memory_record + sku_assignment."""
    import time as _time

    now = int(_time.time())
    sku_addr = f"0x{d1:x}.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0.0x0"
    chunk_id = f"{_SHARED_CHUNK_PREFIX}{record_id}"

    _ensure_source_doc(conn)

    conn.execute(
        "INSERT OR IGNORE INTO chunks "
        "(chunk_id, document_id, source_id, chunk_index, content, content_hash, "
        " token_estimate, chunk_strategy, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
        (chunk_id, _SHARED_DOC_ID, _SHARED_SOURCE_ID, 0, "test", "h", 1, "fixed", now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO memory_records "
        "(record_id, source_id, document_id, chunk_id, content, content_hash, "
        " token_estimate, sku_address, lifecycle_state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
        (
            record_id,
            _SHARED_SOURCE_ID,
            _SHARED_DOC_ID,
            chunk_id,
            "test content",
            "hash_rec",
            1,
            sku_addr,
            now,
        ),
    )
    conn.execute(
        "INSERT OR IGNORE INTO sku_assignments "
        "(assignment_id, record_id, sku_address, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, "
        " raw_scores_json, d1_confidence, classifier_version, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, 0.9, 'test', 'v1', ?)",
        (f"asgn_{record_id}", record_id, sku_addr, d1, "{}", now),
    )


# ── Step 1: SKU construction ──────────────────────────────────────────────────


@pytest.mark.unit
class TestStep1ConstructSku:
    def test_none_d1_gives_none_pattern(self) -> None:
        plan = _plan("hello", query_d1=None)
        d1, pattern = _step1_construct_sku_query(plan)
        assert d1 is None
        assert pattern is None

    def test_d1_gives_hex_pattern(self) -> None:
        plan = _plan("architecture design", query_d1=0x5)
        d1, pattern = _step1_construct_sku_query(plan)
        assert d1 == 0x5
        assert pattern == "0x5"

    def test_d1_zero_gives_0x0(self) -> None:
        plan = _plan("observed data", query_d1=0x0)
        d1, pattern = _step1_construct_sku_query(plan)
        assert d1 == 0x0
        assert pattern == "0x0"


# ── Step 2: Exact SKU match ───────────────────────────────────────────────────


@pytest.mark.unit
class TestStep2ExactSku:
    def test_no_pattern_returns_empty(self) -> None:
        db = _migrated_db()
        try:
            result = _step2_exact_sku(None, db)
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_empty_vault_returns_empty(self) -> None:
        db = _migrated_db()
        try:
            result = _step2_exact_sku("0x5", db)
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_returns_matching_record(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_001", d1=5)
            result = _step2_exact_sku("0x5", db)
            assert "rec_001" in result
        finally:
            db.unlink(missing_ok=True)

    def test_does_not_return_different_d1(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_001", d1=5)
                _insert_sku_record(conn, "rec_002", d1=7)
            result = _step2_exact_sku("0x5", db)
            assert "rec_001" in result
            assert "rec_002" not in result
        finally:
            db.unlink(missing_ok=True)

    def test_returns_list_of_strings(self) -> None:
        db = _migrated_db()
        try:
            result = _step2_exact_sku("0x5", db)
            assert isinstance(result, list)
            for item in result:
                assert isinstance(item, str)
        finally:
            db.unlink(missing_ok=True)


# ── Step 3: Partial SKU match ─────────────────────────────────────────────────


@pytest.mark.unit
class TestStep3PartialSku:
    def test_none_d1_returns_empty(self) -> None:
        db = _migrated_db()
        try:
            result = _step3_partial_sku(None, db, seen_ids=set())
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_empty_vault_returns_empty(self) -> None:
        db = _migrated_db()
        try:
            result = _step3_partial_sku(5, db, seen_ids=set())
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_returns_matching_record(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_001", d1=5)
            result = _step3_partial_sku(5, db, seen_ids=set())
            assert "rec_001" in result
        finally:
            db.unlink(missing_ok=True)

    def test_seen_ids_excluded(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_001", d1=5)
                _insert_sku_record(conn, "rec_002", d1=5)
            result = _step3_partial_sku(5, db, seen_ids={"rec_001"})
            assert "rec_001" not in result
            assert "rec_002" in result
        finally:
            db.unlink(missing_ok=True)

    def test_different_d1_excluded(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
                _insert_sku_record(conn, "rec_d7", d1=7)
            result = _step3_partial_sku(5, db, seen_ids=set())
            assert "rec_d5" in result
            assert "rec_d7" not in result
        finally:
            db.unlink(missing_ok=True)


# ── Step 4: Sibling traversal (no-op) ─────────────────────────────────────────


@pytest.mark.unit
class TestStep4SiblingTraversal:
    def test_returns_input_unchanged(self) -> None:
        db = _migrated_db()
        try:
            ids = ["rec_a", "rec_b", "rec_c"]
            result = traverse_siblings(ids, db)
            assert result == ids
        finally:
            db.unlink(missing_ok=True)

    def test_empty_input_returns_empty(self) -> None:
        db = _migrated_db()
        try:
            result = traverse_siblings([], db)
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_does_not_add_candidates(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_001", d1=5)
            result = traverse_siblings([], db)
            assert len(result) == 0
        finally:
            db.unlink(missing_ok=True)


# ── Retrieval path assembly ───────────────────────────────────────────────────


@pytest.mark.unit
class TestAssembleRetrievalPath:
    def test_exact_sku_with_d1(self) -> None:
        path = _assemble_retrieval_path("rec", ["exact_sku"], query_d1=5)
        assert path == "exact_sku:D1=0x5"

    def test_partial_sku_with_d1(self) -> None:
        path = _assemble_retrieval_path("rec", ["partial_sku"], query_d1=5)
        assert path == "partial_sku:D1=0x5"

    def test_vector_fallback(self) -> None:
        path = _assemble_retrieval_path("rec", ["vector_fallback"], query_d1=None)
        assert path == "vector_fallback"

    def test_lexical_search(self) -> None:
        path = _assemble_retrieval_path("rec", ["lexical_search"], query_d1=None)
        assert path == "lexical_search"

    def test_multi_step_combination(self) -> None:
        path = _assemble_retrieval_path("rec", ["exact_sku", "vector_fallback"], query_d1=5)
        assert path == "exact_sku:D1=0x5 + vector_fallback"

    def test_no_d1_exact_sku(self) -> None:
        path = _assemble_retrieval_path("rec", ["exact_sku"], query_d1=None)
        assert path == "exact_sku"


# ── run_traversal() integration ───────────────────────────────────────────────


@pytest.mark.unit
class TestRunTraversal:
    def test_returns_list(self) -> None:
        db = _migrated_db()
        try:
            plan = _plan("architecture design", mode="hybrid", query_d1=5)
            result = run_traversal(plan, db)
            assert isinstance(result, list)
        finally:
            db.unlink(missing_ok=True)

    def test_empty_vault_returns_empty(self) -> None:
        db = _migrated_db()
        try:
            plan = _plan("architecture design", mode="hybrid", query_d1=5)
            result = run_traversal(plan, db)
            assert result == []
        finally:
            db.unlink(missing_ok=True)

    def test_sku_match_records_surfaced(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
            plan = _plan("architecture design", mode="lexical_only", query_d1=5)
            result = run_traversal(plan, db)
            ids = [c.record_id for c in result]
            assert "rec_d5" in ids
        finally:
            db.unlink(missing_ok=True)

    def test_sku_d1_match_set_correctly(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
            plan = _plan("architecture design", mode="lexical_only", query_d1=5)
            result = run_traversal(plan, db)
            for c in result:
                if c.record_id == "rec_d5":
                    assert c.sku_d1_match is True
        finally:
            db.unlink(missing_ok=True)

    def test_result_items_are_raw_candidates(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
            plan = _plan("architecture design", mode="lexical_only", query_d1=5)
            result = run_traversal(plan, db)
            for item in result:
                assert isinstance(item, RawCandidate)
        finally:
            db.unlink(missing_ok=True)

    def test_no_duplicate_record_ids(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
            plan = _plan("architecture design", mode="lexical_only", query_d1=5)
            result = run_traversal(plan, db)
            ids = [c.record_id for c in result]
            assert len(ids) == len(set(ids)), "Duplicate record_ids in traversal output"
        finally:
            db.unlink(missing_ok=True)

    def test_max_candidates_respected(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                for i in range(10):
                    _insert_sku_record(conn, f"rec_{i:03d}", d1=5)
            plan = _plan("architecture design", mode="lexical_only", query_d1=5, max_candidates=3)
            result = run_traversal(plan, db)
            assert len(result) <= 3
        finally:
            db.unlink(missing_ok=True)

    def test_retrieval_path_non_empty(self) -> None:
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
            plan = _plan("architecture design", mode="lexical_only", query_d1=5)
            result = run_traversal(plan, db)
            for c in result:
                assert c.retrieval_path != ""
                assert c.retrieval_path != "unknown"
        finally:
            db.unlink(missing_ok=True)

    def test_events_emitted_when_log_provided(self) -> None:
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            plan = _plan("architecture design", mode="hybrid", query_d1=5)
            run_traversal(plan, db, event_log=log)
            events = log.query_by_type("TraversalStepCompleted")
            # Six steps emit at most 7 events (step 5 may emit twice for lexical+vector)
            assert len(events) >= 5
        finally:
            db.unlink(missing_ok=True)

    def test_step4_event_skipped(self) -> None:
        import json

        from cerebra.inspector.sqlite_log import SQLiteEventLog

        db = _migrated_db()
        try:
            log = SQLiteEventLog(db)
            plan = _plan("architecture design", mode="hybrid", query_d1=5)
            run_traversal(plan, db, event_log=log)
            events = log.query_by_type("TraversalStepCompleted")
            step4 = [
                e
                for e in events
                if json.loads(e["data_json"]).get("step_name") == "sibling_traversal"
            ]
            assert len(step4) == 1
            assert json.loads(step4[0]["data_json"])["skipped"] is True
        finally:
            db.unlink(missing_ok=True)

    def test_vector_only_mode_no_sku_steps_produce_candidates(self) -> None:
        # In vector_only mode with numpy unavailable or no embeddings, result = []
        db = _migrated_db()
        try:
            with connect(db) as conn:
                _insert_sku_record(conn, "rec_d5", d1=5)
            # vector_only + no embeddings table data → vector step returns []
            # SKU steps will return the record, but vector_only doesn't affect that
            plan = _plan("hello world", mode="vector_only", query_d1=None)
            result = run_traversal(plan, db)
            # SKU steps also run (D1=None so they return empty); vector returns [] without embeddings
            assert isinstance(result, list)
        finally:
            db.unlink(missing_ok=True)
