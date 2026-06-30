"""
Unit tests: cerebra memory status tower section.

Verifies that the truth tower appears correctly in both text and JSON output
from `cerebra memory status`.
"""

from __future__ import annotations

import json
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

# ── Seeding helpers ───────────────────────────────────────────────────────────


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
                f"content for {record_id}",
                "hr0",
                5,
                "active",
                now,
                1,
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO retrieval_traces "
            "(trace_id, query, mode, plan_json, started_at, finished_at, duration_ms, "
            " candidate_count, selected_count, abstained, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"trace_{record_id}", "test", "sku", "{}", now, now, 1, 1, 1, 0, 1),
        )
        conn.commit()
    finally:
        conn.close()


@dataclass
class _FakeMI:
    record_id: str
    source_id: str
    chunk_id: str
    content_excerpt: str
    source_path: str
    sku_address: None
    score: float
    score_components: dict
    retrieval_path: str
    rank: int


def _make_mi(record_id: str, score: float = 0.70) -> _FakeMI:
    return _FakeMI(
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


def _run(vault: Path, *args: str):
    mock_event_log = MagicMock()
    with (
        patch("cerebra.inspector.sqlite_log.SQLiteEventLog", return_value=mock_event_log),
        patch("cerebra.cli.main._get_vault", return_value=vault),
    ):
        return CliRunner().invoke(cli, list(args), catch_exceptions=False)


# ── Test classes ──────────────────────────────────────────────────────────────


class TestMemoryStatusEmptyTower:
    def test_empty_tower_shows_message(self, vault: Path, session_id: str) -> None:
        result = _run(vault, "memory", "status", "--vault", str(vault))
        assert result.exit_code == 0, result.output
        assert "Truth Tower: empty" in result.output

    def test_empty_tower_json_has_zero_counts(self, vault: Path, session_id: str) -> None:
        result = _run(vault, "memory", "status", "--vault", str(vault), "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "truth_tower" in data
        tt = data["truth_tower"]
        assert tt["t1_count"] == 0
        assert tt["t2_count"] == 0
        assert tt["stale_count"] == 0
        assert tt["t1_items"] == []
        assert tt["t2_items"] == []


class TestMemoryStatusT1Only:
    def test_three_t1_items_render_correctly(self, vault: Path, session_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        for i in range(1, 4):
            _seed_memory_record(db, f"rec_{i:02d}")
        tower = TruthTower(db, session_id)
        for i in range(1, 4):
            tower.promote_to_t1(
                [_make_mi(f"rec_{i:02d}", score=0.7 + i * 0.05)], trace_id=f"trace_rec_{i:02d}"
            )

        result = _run(vault, "memory", "status", "--vault", str(vault))
        assert result.exit_code == 0, result.output
        assert "Truth Tower" in result.output
        assert "3 T1" in result.output
        assert "0 T2" in result.output
        assert "T1 [1]" in result.output
        assert "T1 [2]" in result.output
        assert "T1 [3]" in result.output
        assert "Truth Tower: empty" not in result.output

    def test_t1_json_count_correct(self, vault: Path, session_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        _seed_memory_record(db, "rec_j01")
        TruthTower(db, session_id).promote_to_t1([_make_mi("rec_j01")], trace_id="trace_rec_j01")

        result = _run(vault, "memory", "status", "--vault", str(vault), "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["truth_tower"]["t1_count"] == 1
        assert len(data["truth_tower"]["t1_items"]) == 1


class TestMemoryStatusT1AndT2:
    def test_t2_nested_under_cited_t1(self, vault: Path, session_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        for i in range(1, 4):
            _seed_memory_record(db, f"rec_t_{i:02d}")
        tower = TruthTower(db, session_id)
        t1_items = []
        for i in range(1, 4):
            items = tower.promote_to_t1(
                [_make_mi(f"rec_t_{i:02d}", score=0.75)], trace_id=f"trace_rec_t_{i:02d}"
            )
            t1_items.extend(items)

        # Promote two WM items to T2 citing t1_items[1]
        wm = WorkingMemory(db, session_id)
        wm_a = wm.promote("evidence", None, "evidence A", 0.70)
        wm_b = wm.promote("evidence", None, "evidence B", 0.65)
        t1_anchor = t1_items[1]
        tower.promote_to_t2(wm_a, t1_anchor.tower_item_id)
        tower.promote_to_t2(wm_b, t1_anchor.tower_item_id)

        result = _run(vault, "memory", "status", "--vault", str(vault))
        assert result.exit_code == 0, result.output
        assert "3 T1" in result.output
        assert "2 T2" in result.output
        assert "T2 [1]" in result.output
        assert "T2 [2]" in result.output
        # T2 items cite T1[2] (index 1 = second item)
        assert "^T1[2]" in result.output

    def test_t1_t2_json_shape(self, vault: Path, session_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        _seed_memory_record(db, "rec_jt1")
        tower = TruthTower(db, session_id)
        t1s = tower.promote_to_t1([_make_mi("rec_jt1")], trace_id="trace_rec_jt1")
        wm = WorkingMemory(db, session_id)
        wm_item = wm.promote("evidence", None, "wm for t2", 0.6)
        tower.promote_to_t2(wm_item, t1s[0].tower_item_id)

        result = _run(vault, "memory", "status", "--vault", str(vault), "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        tt = data["truth_tower"]
        assert tt["t1_count"] == 1
        assert tt["t2_count"] == 1
        assert len(tt["t1_items"]) == 1
        assert len(tt["t2_items"]) == 1
        assert tt["t2_items"][0]["t1_citation_id"] == t1s[0].tower_item_id


class TestMemoryStatusStalT2:
    def test_stale_t2_shows_stale_marker(self, vault: Path, session_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        _seed_memory_record(db, "rec_stale01")
        tower = TruthTower(db, session_id)
        t1s = tower.promote_to_t1([_make_mi("rec_stale01")], trace_id="trace_rec_stale01")
        wm = WorkingMemory(db, session_id)
        wm_item = wm.promote("evidence", None, "wm for stale t2", 0.6)
        tower.promote_to_t2(wm_item, t1s[0].tower_item_id)

        # Force-stale the T2 by evicting the T1 in the DB and calling mark_stale
        conn = connect(db)
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = 1 WHERE tower_item_id = ?",
            (t1s[0].tower_item_id,),
        )
        conn.commit()
        conn.close()
        tower.mark_stale_from_t1_eviction(t1s[0].tower_item_id)

        result = _run(vault, "memory", "status", "--vault", str(vault))
        assert result.exit_code == 0, result.output
        assert "[stale]" in result.output

    def test_stale_count_nonzero_in_json(self, vault: Path, session_id: str) -> None:
        db = vault / "data" / "cerebra.db"
        _seed_memory_record(db, "rec_stale02")
        tower = TruthTower(db, session_id)
        t1s = tower.promote_to_t1([_make_mi("rec_stale02")], trace_id="trace_rec_stale02")
        wm = WorkingMemory(db, session_id)
        wm_item = wm.promote("evidence", None, "wm for stale count", 0.6)
        tower.promote_to_t2(wm_item, t1s[0].tower_item_id)

        conn = connect(db)
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = 1 WHERE tower_item_id = ?",
            (t1s[0].tower_item_id,),
        )
        conn.commit()
        conn.close()
        tower.mark_stale_from_t1_eviction(t1s[0].tower_item_id)

        result = _run(vault, "memory", "status", "--vault", str(vault), "--format", "json")
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["truth_tower"]["stale_count"] >= 1
        stale_t2 = data["truth_tower"]["t2_items"][0]
        assert stale_t2["is_stale"] is True
