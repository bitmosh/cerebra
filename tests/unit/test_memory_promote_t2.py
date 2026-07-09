# SPDX-License-Identifier: Apache-2.0
"""
Unit tests: cerebra memory promote --tier 2 --cite <t1_item_id>

Tests use a real throw-away SQLite DB for the session/WM/tower state
and mock only the vault_lock and SQLiteEventLog (to avoid filesystem side effects).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cerebra.cli.main import cli
from cerebra.cognition.truth_tower import TruthTower
from cerebra.cognition.working_memory import WorkingMemory, new_session
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations

# ── DB seeding helpers ────────────────────────────────────────────────────────


def _seed_memory_record(db_path: Path, record_id: str) -> None:
    now = int(time.time())
    src_id = f"src_{record_id}"
    doc_id = f"doc_{record_id}"
    chunk_id = f"chk_{record_id}"
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(source_id, canonical_path, content_hash, size_bytes, "
            " detected_type, detection_confidence, parser_status, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (src_id, f"/test/{record_id}", "h0", 1, "markdown", 1.0, "done", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO documents "
            "(document_id, source_id, document_type, normalization_confidence, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?)",
            (doc_id, src_id, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO chunks "
            "(chunk_id, document_id, source_id, heading_path, chunk_index, "
            " depth, content, content_hash, token_estimate, chunk_strategy, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                chunk_id,
                doc_id,
                src_id,
                "",
                0,
                0,
                "test content",
                "hc0",
                5,
                "fixed",
                "active",
                now,
                1,
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO memory_records "
            "(record_id, record_type, source_id, document_id, chunk_id, "
            " content, content_hash, token_estimate, lifecycle_state, "
            " created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                record_id,
                "source_chunk",
                src_id,
                doc_id,
                chunk_id,
                "test content",
                "hr0",
                5,
                "active",
                now,
                1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_retrieval_trace(db_path: Path, trace_id: str = "trace_test") -> str:
    now = int(time.time())
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO retrieval_traces "
            "(trace_id, query, mode, plan_json, started_at, finished_at, duration_ms, "
            " candidate_count, selected_count, abstained, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (trace_id, "test query", "sku", "{}", now, now, 1, 3, 2, 0, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return trace_id


@dataclass
class _FakeMemoryItem:
    record_id: str
    source_id: str
    chunk_id: str
    content_excerpt: str
    source_path: str
    sku_address: str | None
    score: float
    score_components: dict
    retrieval_path: str
    rank: int


def _make_mi(record_id: str, score: float = 0.70) -> _FakeMemoryItem:
    return _FakeMemoryItem(
        record_id=record_id,
        source_id=f"src_{record_id}",
        chunk_id=f"chk_{record_id}",
        content_excerpt=f"content for {record_id}",
        source_path=f"/test/{record_id}.md",
        sku_address=None,
        score=score,
        score_components={},
        retrieval_path="vector",
        rank=1,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    db = tmp_path / "data" / "cerebra.db"
    run_migrations(db)
    return tmp_path


@pytest.fixture()
def session_id(vault: Path) -> str:
    db = vault / "data" / "cerebra.db"
    return new_session(db, str(vault))


@pytest.fixture()
def wm_item_id(vault: Path, session_id: str) -> str:
    """Promote a synthetic WM item; return its item_id."""
    db = vault / "data" / "cerebra.db"
    wm = WorkingMemory(db, session_id)
    item = wm.promote(
        slot_type="evidence",
        record_id=None,
        content_summary="test content for T2 promotion",
        salience_score=0.75,
        is_pinned=False,
    )
    return item.item_id


@pytest.fixture()
def t1_item_id(vault: Path, session_id: str) -> str:
    """Seed a record, seed a trace, promote to T1; return the tower_item_id."""
    db = vault / "data" / "cerebra.db"
    _seed_memory_record(db, "rec_t1seed")
    _seed_retrieval_trace(db, "trace_t1seed")
    tower = TruthTower(db, session_id)
    items = tower.promote_to_t1([_make_mi("rec_t1seed")], trace_id="trace_t1seed")
    assert items, "Expected at least one T1 item"
    return items[0].tower_item_id


def _run(vault: Path, *args: str):
    """Invoke CLI with mocked vault_lock and SQLiteEventLog."""
    mock_event_log = MagicMock()
    with (
        patch("cerebra.cli.lockfile.vault_lock"),
        patch("cerebra.inspector.sqlite_log.SQLiteEventLog", return_value=mock_event_log),
        patch("cerebra.cli.main._get_vault", return_value=vault),
    ):
        return CliRunner().invoke(cli, list(args), catch_exceptions=False)


def _run_real_log(vault: Path, *args: str):
    """Invoke CLI with mocked vault_lock only — SQLiteEventLog writes to the real DB."""
    with (
        patch("cerebra.cli.lockfile.vault_lock"),
        patch("cerebra.cli.main._get_vault", return_value=vault),
    ):
        return CliRunner().invoke(cli, list(args), catch_exceptions=False)


# ── Happy path ────────────────────────────────────────────────────────────────


class TestT2HappyPath:
    def test_promote_by_wm_item_id(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 0, result.output
        assert "Promoted to T2:" in result.output
        assert t1_item_id in result.output
        assert session_id in result.output
        assert "Pinned:    no" in result.output

    def test_promote_by_record_id(self, vault: Path, session_id: str, t1_item_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        _seed_memory_record(db, "rec_test01")
        wm = WorkingMemory(db, session_id)
        wm.promote(
            slot_type="evidence",
            record_id="rec_test01",
            content_summary="test content",
            salience_score=0.80,
        )

        result = _run(
            vault,
            "memory",
            "promote",
            "rec_test01",
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 0, result.output
        assert "Promoted to T2:" in result.output

    def test_promote_with_pin(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--pin",
            "--vault",
            str(vault),
        )
        assert result.exit_code == 0, result.output
        assert "Pinned:    yes" in result.output

        # Verify it's actually pinned in the DB
        db = vault / "data" / "cerebra.db"
        tower = TruthTower(db, session_id)
        t2_items = tower.load_tier(2)
        assert any(i.is_pinned for i in t2_items)

    def test_t2_item_appears_in_db(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        db = vault / "data" / "cerebra.db"
        tower = TruthTower(db, session_id)
        t2_items = tower.load_tier(2)
        assert len(t2_items) >= 1
        assert t2_items[0].t1_citation_id == t1_item_id


# ── Validation errors ─────────────────────────────────────────────────────────


class TestT2ValidationErrors:
    def test_missing_cite_flag(self, vault: Path, session_id: str, wm_item_id: str) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "--cite is required" in result.output

    def test_cited_t1_not_found(self, vault: Path, session_id: str, wm_item_id: str) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            "twi_nonexistent00000",
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "Error:" in result.output

    def test_cited_item_is_tier2_not_t1(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        # First create a T2 item, then try to cite it as the anchor
        db = vault / "data" / "cerebra.db"
        wm = WorkingMemory(db, session_id)
        all_items = wm.load_all_active()
        wm_item = next(i for items in all_items.values() for i in items if i.item_id == wm_item_id)
        tower = TruthTower(db, session_id)
        t2_item = tower.promote_to_t2(wm_item, t1_item_id)

        # Now add a second WM item to try promoting to T2 citing the T2
        item2 = wm.promote(
            slot_type="hypothesis",
            record_id=None,
            content_summary="second item",
            salience_score=0.6,
        )

        result = _run(
            vault,
            "memory",
            "promote",
            item2.item_id,
            "--tier",
            "2",
            "--cite",
            t2_item.tower_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "Error:" in result.output

    def test_cited_t1_evicted_born_stale(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        # Evict the T1 item directly in the DB
        db = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = 1 WHERE tower_item_id = ?",
            (t1_item_id,),
        )
        conn.commit()
        conn.close()

        result = _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert (
            "evicted" in result.output.lower()
            or "born-stale" in result.output.lower()
            or "Error:" in result.output
        )

    def test_wm_item_evicted(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        db = vault / "data" / "cerebra.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE working_memory_items SET evicted_at = 1 WHERE item_id = ?",
            (wm_item_id,),
        )
        conn.commit()
        conn.close()

        result = _run(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "evicted" in result.output.lower()

    def test_wm_item_not_in_session(self, vault: Path, session_id: str, t1_item_id: str) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            "wmi_doesnotexist0",
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "not found" in result.output.lower()

    def test_ambiguous_positional_arg(self, vault: Path, session_id: str, t1_item_id: str) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            "badprefix_abc123",
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "rec_" in result.output or "wmi_" in result.output

    def test_no_active_session(self, tmp_path: Path, t1_item_id: str = "twi_fake") -> None:
        # Fresh vault with no session
        (tmp_path / "data").mkdir()
        db = tmp_path / "data" / "cerebra.db"
        run_migrations(db)

        result = _run(
            tmp_path,
            "memory",
            "promote",
            "wmi_abc",
            "--tier",
            "2",
            "--cite",
            "twi_fake",
            "--vault",
            str(tmp_path),
        )
        assert result.exit_code == 2
        assert "session" in result.output.lower()

    def test_tier1_still_unimplemented(self, vault: Path) -> None:
        result = _run(
            vault,
            "memory",
            "promote",
            "wmi_abc",
            "--tier",
            "1",
            "--vault",
            str(vault),
        )
        assert result.exit_code == 2
        assert "not yet implemented" in result.output.lower()


# ── Event emission ────────────────────────────────────────────────────────────


class TestT2EventEmission:
    def test_tower_item_promoted_event_fires(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        """TowerItemPromoted with tier=2 fires after a successful T2 promotion."""
        import json

        db = vault / "data" / "cerebra.db"
        result = _run_real_log(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 0, result.output
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT event_type, data_json FROM inspector_events "
                "WHERE event_type = 'TowerItemPromoted' "
                "ORDER BY timestamp DESC LIMIT 1"
            ).fetchall()
        finally:
            conn.close()
        assert rows, "TowerItemPromoted event not found"
        data = json.loads(rows[0]["data_json"])
        assert data.get("tier") == 2

    def test_tower_cross_reference_added_event_fires(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        """TowerCrossReferenceAdded fires alongside TowerItemPromoted."""
        db = vault / "data" / "cerebra.db"
        result = _run_real_log(
            vault,
            "memory",
            "promote",
            wm_item_id,
            "--tier",
            "2",
            "--cite",
            t1_item_id,
            "--vault",
            str(vault),
        )
        assert result.exit_code == 0, result.output
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT event_type FROM inspector_events "
                "WHERE event_type = 'TowerCrossReferenceAdded'"
            ).fetchall()
        finally:
            conn.close()
        assert rows, "TowerCrossReferenceAdded event not found"


# ── Idempotency / lockfile ────────────────────────────────────────────────────


class TestT2Lockfile:
    def test_lockfile_acquired_on_write(
        self, vault: Path, session_id: str, wm_item_id: str, t1_item_id: str
    ) -> None:
        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=False)
        mock_event_log = MagicMock()

        with (
            patch("cerebra.cli.lockfile.vault_lock", return_value=mock_lock) as mock_vault_lock,
            patch("cerebra.inspector.sqlite_log.SQLiteEventLog", return_value=mock_event_log),
            patch("cerebra.cli.main._get_vault", return_value=vault),
        ):
            result = CliRunner().invoke(
                cli,
                [
                    "memory",
                    "promote",
                    wm_item_id,
                    "--tier",
                    "2",
                    "--cite",
                    t1_item_id,
                    "--vault",
                    str(vault),
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0, result.output
        mock_vault_lock.assert_called_once()
