"""Phase 11 unit tests — LifecycleManager state machine, FTS5 sync, re-ingestion block.

Run with: pytest tests/unit/test_lifecycle.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cerebra.cognition._constants import SYNTHETIC_CHUNK_ID, SYNTHETIC_DOCUMENT_ID, SYNTHETIC_SOURCE_ID
from cerebra.memory.lifecycle import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    LifecycleManager,
    RecordNotFoundError,
)
from cerebra.storage.migrations import run_migrations


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "cerebra.db"
    run_migrations(p)
    return p


def _insert_record(
    db_path: Path,
    record_id: str,
    *,
    lifecycle_state: str = "active",
    record_type: str = "source_chunk",
    content: str = "test content for lifecycle",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        INSERT INTO memory_records (
            record_id, record_type, source_id, document_id, chunk_id,
            content, content_hash, token_estimate, lifecycle_state, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1700000000000)
        """,
        (
            record_id, record_type,
            SYNTHETIC_SOURCE_ID, SYNTHETIC_DOCUMENT_ID, SYNTHETIC_CHUNK_ID,
            content, "deadbeef00000000", len(content.split()),
            lifecycle_state,
        ),
    )
    conn.commit()
    conn.close()


def _get_state(db_path: Path, record_id: str) -> str | None:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT lifecycle_state FROM memory_records WHERE record_id = ?", (record_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── Valid transitions ─────────────────────────────────────────────────────────


class TestValidTransitions:
    def test_active_to_archived(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_001", lifecycle_state="active")
        mgr = LifecycleManager(db_path)
        prev = mgr.archive("rec_001")
        assert prev == "active"
        assert _get_state(db_path, "rec_001") == "archived"

    def test_active_to_tombstoned(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_002", lifecycle_state="active")
        mgr = LifecycleManager(db_path)
        prev = mgr.tombstone("rec_002")
        assert prev == "active"
        assert _get_state(db_path, "rec_002") == "tombstoned"

    def test_archived_to_active_restore(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_003", lifecycle_state="archived")
        mgr = LifecycleManager(db_path)
        prev = mgr.restore("rec_003")
        assert prev == "archived"
        assert _get_state(db_path, "rec_003") == "active"

    def test_archived_to_tombstoned(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_004", lifecycle_state="archived")
        mgr = LifecycleManager(db_path)
        prev = mgr.tombstone("rec_004")
        assert prev == "archived"
        assert _get_state(db_path, "rec_004") == "tombstoned"

    def test_valid_transitions_set_is_complete(self) -> None:
        assert ("active", "archived") in VALID_TRANSITIONS
        assert ("active", "tombstoned") in VALID_TRANSITIONS
        assert ("archived", "active") in VALID_TRANSITIONS
        assert ("archived", "tombstoned") in VALID_TRANSITIONS
        assert len(VALID_TRANSITIONS) == 4


# ── Invalid transitions ───────────────────────────────────────────────────────


class TestInvalidTransitions:
    def test_tombstoned_is_terminal(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_010", lifecycle_state="tombstoned")
        mgr = LifecycleManager(db_path)
        with pytest.raises(InvalidTransitionError):
            mgr.restore("rec_010")

    def test_tombstoned_to_archived_blocked(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_011", lifecycle_state="tombstoned")
        mgr = LifecycleManager(db_path)
        with pytest.raises(InvalidTransitionError):
            mgr.archive("rec_011")

    def test_tombstoned_to_tombstoned_noop(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_012", lifecycle_state="tombstoned")
        mgr = LifecycleManager(db_path)
        # Same-state transition returns current state without raising.
        prev = mgr.transition("rec_012", "tombstoned")
        assert prev == "tombstoned"
        assert _get_state(db_path, "rec_012") == "tombstoned"

    def test_active_to_active_noop(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_013", lifecycle_state="active")
        mgr = LifecycleManager(db_path)
        prev = mgr.transition("rec_013", "active")
        assert prev == "active"

    def test_unknown_target_state_raises(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_014", lifecycle_state="active")
        mgr = LifecycleManager(db_path)
        from cerebra.memory.lifecycle import LifecycleError
        with pytest.raises(LifecycleError):
            mgr.transition("rec_014", "warm")

    def test_missing_record_raises(self, db_path: Path) -> None:
        mgr = LifecycleManager(db_path)
        with pytest.raises(RecordNotFoundError):
            mgr.archive("rec_doesnotexist")


# ── get_state ─────────────────────────────────────────────────────────────────


class TestGetState:
    def test_returns_current_state(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_020", lifecycle_state="archived")
        mgr = LifecycleManager(db_path)
        assert mgr.get_state("rec_020") == "archived"

    def test_returns_none_for_missing(self, db_path: Path) -> None:
        mgr = LifecycleManager(db_path)
        assert mgr.get_state("rec_doesnotexist") is None


# ── batch_transition ──────────────────────────────────────────────────────────


class TestBatchTransition:
    def test_transitions_all(self, db_path: Path) -> None:
        for i in range(3):
            _insert_record(db_path, f"rec_03{i}", lifecycle_state="active")
        mgr = LifecycleManager(db_path)
        result = mgr.batch_transition(["rec_030", "rec_031", "rec_032"], "archived")
        assert all(v == "active" for v in result.values())
        for i in range(3):
            assert _get_state(db_path, f"rec_03{i}") == "archived"

    def test_raises_on_first_failure(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_040", lifecycle_state="active")
        mgr = LifecycleManager(db_path)
        with pytest.raises(RecordNotFoundError):
            mgr.batch_transition(["rec_040", "rec_doesnotexist"], "archived")


# ── cycle_episode records — tombstone scoped to memory_records only ───────────


class TestCycleEpisodeTombstone:
    def test_cycle_episode_memory_record_can_be_tombstoned(self, db_path: Path) -> None:
        _insert_record(db_path, "ep_aabbccddeeff", record_type="cycle_episode")
        mgr = LifecycleManager(db_path)
        mgr.tombstone("ep_aabbccddeeff")
        assert _get_state(db_path, "ep_aabbccddeeff") == "tombstoned"

    def test_cycle_episode_records_table_unaffected(self, db_path: Path) -> None:
        """Tombstoning a cycle_episode memory_records row must not touch cycle_episode_records."""
        _insert_record(db_path, "ep_bbccddeeff00", record_type="cycle_episode")
        mgr = LifecycleManager(db_path)
        mgr.tombstone("ep_bbccddeeff00")
        # cycle_episode_records table exists and is not altered by lifecycle.
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM cycle_episode_records").fetchone()[0]
        conn.close()
        assert count == 0  # nothing was written there; tombstone didn't touch it


# ── Re-ingestion block ────────────────────────────────────────────────────────


class TestReingestionBlock:
    def test_tombstoned_record_survives_mark_stale(self, db_path: Path) -> None:
        """mark_records_stale_for_source must not override tombstoned state."""
        from cerebra.storage.sqlite_store import SQLiteStore

        _insert_record(
            db_path, "rec_050",
            lifecycle_state="tombstoned",
        )
        # Manually set source_id to something we can target.
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE memory_records SET source_id = 'src_test' WHERE record_id = 'rec_050'"
        )
        conn.commit()
        conn.close()

        store = SQLiteStore(db_path)
        store.mark_records_stale_for_source("src_test")

        assert _get_state(db_path, "rec_050") == "tombstoned"

    def test_active_record_marked_stale_for_source(self, db_path: Path) -> None:
        """Active records are still marked stale normally."""
        from cerebra.storage.sqlite_store import SQLiteStore

        _insert_record(db_path, "rec_051", lifecycle_state="active")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE memory_records SET source_id = 'src_test2' WHERE record_id = 'rec_051'"
        )
        conn.commit()
        conn.close()

        store = SQLiteStore(db_path)
        store.mark_records_stale_for_source("src_test2")

        assert _get_state(db_path, "rec_051") == "stale"

    def test_insert_or_ignore_preserves_tombstone_on_reingest(self, db_path: Path) -> None:
        """insert_records_batch skips records whose record_id already exists (tombstoned)."""
        from cerebra.storage.sqlite_store import SQLiteStore

        _insert_record(db_path, "rec_052", lifecycle_state="tombstoned")

        store = SQLiteStore(db_path)
        store.insert_records_batch([{
            "record_id": "rec_052",
            "record_type": "source_chunk",
            "source_id": SYNTHETIC_SOURCE_ID,
            "document_id": SYNTHETIC_DOCUMENT_ID,
            "chunk_id": SYNTHETIC_CHUNK_ID,
            "content": "new content that should be ignored",
            "content_hash": "newnewhash00000",
            "token_estimate": 5,
            "sku_address": None,
            "sku_assigned_at": None,
            "lifecycle_state": "active",
            "created_at": 1800000000000,
            "schema_version": 1,
        }])

        assert _get_state(db_path, "rec_052") == "tombstoned"
        # Content was not overwritten.
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT content FROM memory_records WHERE record_id = 'rec_052'"
        ).fetchone()
        conn.close()
        assert row[0] == "test content for lifecycle"


# ── FTS5 sync ─────────────────────────────────────────────────────────────────


class TestFTSSync:
    def _build_fts(self, db_path: Path) -> None:
        from cerebra.storage.lexical import build_fts_index
        build_fts_index(db_path)

    def _fts_count(self, db_path: Path, record_id: str) -> int:
        from cerebra.storage.lexical import FTS_TABLE
        conn = sqlite3.connect(db_path)
        # FTS5 external content: query the FTS table for the rowid of the record.
        rowid_row = conn.execute(
            "SELECT rowid FROM memory_records WHERE record_id = ?", (record_id,)
        ).fetchone()
        if rowid_row is None:
            conn.close()
            return 0
        count = conn.execute(
            f"SELECT COUNT(*) FROM {FTS_TABLE} WHERE rowid = ?", (rowid_row[0],)
        ).fetchone()[0]
        conn.close()
        return count

    def test_tombstone_removes_from_fts(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_060", content="unique tombstone fts test content")
        self._build_fts(db_path)
        assert self._fts_count(db_path, "rec_060") == 1

        mgr = LifecycleManager(db_path)
        mgr.tombstone("rec_060")
        assert self._fts_count(db_path, "rec_060") == 0

    def test_archive_removes_from_fts(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_061", content="unique archive fts test content")
        self._build_fts(db_path)
        assert self._fts_count(db_path, "rec_061") == 1

        mgr = LifecycleManager(db_path)
        mgr.archive("rec_061")
        assert self._fts_count(db_path, "rec_061") == 0

    def test_restore_readds_to_fts(self, db_path: Path) -> None:
        _insert_record(db_path, "rec_062", lifecycle_state="archived",
                       content="unique restore fts test content")
        self._build_fts(db_path)
        # Archived record is not in FTS (build_fts_index only indexes active).
        assert self._fts_count(db_path, "rec_062") == 0

        mgr = LifecycleManager(db_path)
        mgr.restore("rec_062")
        assert self._fts_count(db_path, "rec_062") == 1

    def test_no_fts_table_does_not_raise(self, db_path: Path) -> None:
        """Lifecycle transitions work even if FTS index hasn't been built yet."""
        _insert_record(db_path, "rec_063")
        mgr = LifecycleManager(db_path)
        mgr.tombstone("rec_063")  # should not raise
        assert _get_state(db_path, "rec_063") == "tombstoned"
