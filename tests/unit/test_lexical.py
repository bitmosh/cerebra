"""Unit tests for cerebra/storage/lexical.py."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.index_state import get_state, mark_updated, seed_index_state
from cerebra.storage.lexical import (
    FTS_TABLE,
    build_fts_index,
    is_lexical_stale,
    search,
    update_fts_index,
)
from cerebra.storage.migrations import run_migrations
from cerebra.storage.db import connect


# ── Fixtures and helpers ───────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    run_migrations(db_path)
    return db_path


def _insert_record(
    db_path: Path,
    *,
    record_id: str,
    content: str,
    lifecycle_state: str = "active",
    created_at: int | None = None,
) -> str:
    """Insert a minimal source→document→chunk→memory_record chain."""
    now = created_at if created_at is not None else int(time.time())
    src_id = f"src_{record_id}"
    doc_id = f"doc_{record_id}"
    chk_id = f"chk_{record_id}"
    content_hash = f"hash_{record_id}"

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources (
                source_id, canonical_path, content_hash, size_bytes,
                detected_type, detection_confidence, lifecycle_state,
                created_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (src_id, f"/fake/{record_id}.md", content_hash, 100,
             "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            """
            INSERT INTO documents (
                document_id, source_id, document_type, normalization_confidence,
                lifecycle_state, created_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, src_id, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            """
            INSERT INTO chunks (
                chunk_id, document_id, source_id, heading_path, chunk_index,
                depth, content, content_hash, token_estimate, chunk_strategy,
                lifecycle_state, created_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chk_id, doc_id, src_id, "", 0, 0, content, content_hash,
             len(content.split()), "fixed", "active", now, 1),
        )
        conn.execute(
            """
            INSERT INTO memory_records (
                record_id, record_type, source_id, document_id, chunk_id,
                content, content_hash, token_estimate, lifecycle_state,
                created_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, "source_chunk", src_id, doc_id, chk_id,
             content, content_hash, len(content.split()),
             lifecycle_state, now, 1),
        )
    return record_id


# ── build_fts_index ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestBuildFtsIndex:
    def test_creates_fts_table(self, db: Path) -> None:
        build_fts_index(db)
        with connect(db) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (FTS_TABLE,),
            ).fetchone()
        assert row is not None

    def test_returns_active_record_count(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="hello world")
        _insert_record(db, record_id="rec_002", content="foo bar", lifecycle_state="archived")
        count = build_fts_index(db)
        assert count == 1  # only active record counted

    def test_indexes_existing_records(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="neural network training")
        build_fts_index(db)
        results = search(db, "neural")
        assert len(results) == 1
        assert results[0][0] == "rec_001"

    def test_idempotent_rebuild(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="hello world")
        build_fts_index(db)
        build_fts_index(db)  # second build should not error or duplicate
        results = search(db, "hello")
        assert len(results) == 1

    def test_updates_index_state(self, db: Path) -> None:
        seed_index_state(db)
        build_fts_index(db)
        state = get_state(db, "lexical")
        assert state is not None
        assert state["last_updated_at"] > 0

    def test_seeds_index_state_if_missing(self, db: Path) -> None:
        # index_state not seeded yet — build_fts_index should seed it
        build_fts_index(db)
        state = get_state(db, "lexical")
        assert state is not None

    def test_emits_event(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        _insert_record(db, record_id="rec_001", content="hello")
        build_fts_index(db, event_log=log)
        events = log.query_by_type("LexicalIndexUpdated")
        assert len(events) == 1
        data = json.loads(events[0]["data_json"])
        assert "records_indexed" in data
        assert "duration_ms" in data

    def test_no_event_without_log(self, db: Path) -> None:
        # Passing no event_log should not raise
        count = build_fts_index(db)
        assert isinstance(count, int)


# ── update_fts_index ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestUpdateFtsIndex:
    def test_new_record_becomes_searchable(self, db: Path) -> None:
        build_fts_index(db)
        _insert_record(db, record_id="rec_new", content="gradient descent optimizer")
        update_fts_index(db, ["rec_new"])
        results = search(db, "gradient")
        ids = [r[0] for r in results]
        assert "rec_new" in ids

    def test_returns_count_of_indexed_records(self, db: Path) -> None:
        build_fts_index(db)
        _insert_record(db, record_id="rec_a", content="alpha")
        _insert_record(db, record_id="rec_b", content="beta")
        count = update_fts_index(db, ["rec_a", "rec_b"])
        assert count == 2

    def test_empty_list_returns_zero(self, db: Path) -> None:
        build_fts_index(db)
        count = update_fts_index(db, [])
        assert count == 0

    def test_nonexistent_record_id_ignored(self, db: Path) -> None:
        build_fts_index(db)
        count = update_fts_index(db, ["rec_does_not_exist"])
        assert count == 0

    def test_updates_index_state(self, db: Path) -> None:
        build_fts_index(db)
        _insert_record(db, record_id="rec_new", content="hello")
        t_before = get_state(db, "lexical")["last_updated_at"]
        time.sleep(1)  # ensure timestamp advances
        update_fts_index(db, ["rec_new"])
        t_after = get_state(db, "lexical")["last_updated_at"]
        assert t_after >= t_before

    def test_emits_event(self, db: Path) -> None:
        log = SQLiteEventLog(db)
        build_fts_index(db)
        _insert_record(db, record_id="rec_new", content="hello")
        update_fts_index(db, ["rec_new"], event_log=log)
        events = log.query_by_type("LexicalIndexUpdated")
        assert len(events) == 1
        data = json.loads(events[0]["data_json"])
        assert data["records_indexed"] == 1

    def test_re_index_does_not_duplicate_results(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="singular content")
        build_fts_index(db)
        update_fts_index(db, ["rec_001"])  # re-index same record
        results = search(db, "singular")
        # Should appear exactly once despite being re-indexed
        assert len(results) == 1


# ── search ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSearch:
    def test_basic_match(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="the quick brown fox")
        build_fts_index(db)
        results = search(db, "quick")
        assert len(results) == 1
        assert results[0][0] == "rec_001"

    def test_no_match_returns_empty(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="hello world")
        build_fts_index(db)
        results = search(db, "zzzzunlikelyterm")
        assert results == []

    def test_returns_record_id_and_rank(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="machine learning")
        build_fts_index(db)
        results = search(db, "machine")
        assert len(results) == 1
        record_id, rank = results[0]
        assert isinstance(record_id, str)
        assert isinstance(rank, float)

    def test_rank_is_negative(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="hello world")
        build_fts_index(db)
        results = search(db, "hello")
        assert results[0][1] < 0  # FTS5 BM25 rank is negative

    def test_filters_archived_records(self, db: Path) -> None:
        _insert_record(db, record_id="rec_active", content="hello world")
        _insert_record(db, record_id="rec_archived", content="hello world", lifecycle_state="archived")
        build_fts_index(db)
        results = search(db, "hello")
        ids = [r[0] for r in results]
        assert "rec_active" in ids
        assert "rec_archived" not in ids

    def test_limit_respected(self, db: Path) -> None:
        for i in range(5):
            _insert_record(db, record_id=f"rec_{i:03}", content=f"common term unique_{i}")
        build_fts_index(db)
        results = search(db, "common", limit=3)
        assert len(results) <= 3

    def test_returns_empty_if_fts_table_missing(self, db: Path) -> None:
        # Don't build index — FTS table doesn't exist
        results = search(db, "anything")
        assert results == []

    def test_multiple_records_ranked(self, db: Path) -> None:
        # Record with more occurrences of the term should rank higher
        _insert_record(db, record_id="rec_many", content="cat cat cat")
        _insert_record(db, record_id="rec_one", content="cat dog bird")
        build_fts_index(db)
        results = search(db, "cat")
        assert len(results) == 2
        # More negative rank = better match = should be first
        assert results[0][1] <= results[1][1]


# ── is_lexical_stale (drift detection) ────────────────────────────────────────


@pytest.mark.unit
class TestIsLexicalStale:
    def test_stale_when_index_state_missing(self, db: Path) -> None:
        # No seed, no build — index_state has no lexical row
        assert is_lexical_stale(db) is True

    def test_stale_when_never_built(self, db: Path) -> None:
        seed_index_state(db)
        assert is_lexical_stale(db) is True

    def test_not_stale_after_build_with_no_records(self, db: Path) -> None:
        build_fts_index(db)
        assert is_lexical_stale(db) is False

    def test_not_stale_after_build_with_records(self, db: Path) -> None:
        _insert_record(db, record_id="rec_001", content="hello")
        build_fts_index(db)
        assert is_lexical_stale(db) is False

    def test_stale_after_new_record_without_update(self, db: Path) -> None:
        """Drift detection: add record after build without updating FTS."""
        build_fts_index(db)
        # Insert a record with created_at well in the future relative to last build
        future_ts = int(time.time()) + 3600
        _insert_record(db, record_id="rec_new", content="new content", created_at=future_ts)
        assert is_lexical_stale(db) is True

    def test_not_stale_after_update_fts(self, db: Path) -> None:
        build_fts_index(db)
        future_ts = int(time.time()) + 3600
        _insert_record(db, record_id="rec_new", content="new", created_at=future_ts)
        assert is_lexical_stale(db) is True
        update_fts_index(db, ["rec_new"])
        assert is_lexical_stale(db) is False

    def test_stale_only_checks_active_records(self, db: Path) -> None:
        build_fts_index(db)
        # Archived record with future timestamp should NOT trigger staleness
        future_ts = int(time.time()) + 3600
        _insert_record(
            db, record_id="rec_archived", content="archived",
            lifecycle_state="archived", created_at=future_ts,
        )
        assert is_lexical_stale(db) is False
