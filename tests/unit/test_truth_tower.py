"""
Unit tests for TruthTower and TowerItem (Phase 5 Step 5).

All tests use a throw-away SQLite DB (no vault on disk required).
MemoryItems are constructed directly; no real retrieval pipeline needed.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from cerebra.cognition._constants import TOWER_CAPACITIES
from cerebra.cognition.truth_tower import TowerItem, TowerPromotionError, TruthTower
from cerebra.cognition.working_memory import WorkingMemory, WorkingMemoryItem, new_session
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations


# ── helpers ───────────────────────────────────────────────────────────────────


def _fresh_db() -> tuple[Path, str]:
    """Return (db_path, session_id) for a throw-away DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    run_migrations(db_path)
    session_id = new_session(db_path, vault_path=str(db_path.parent))
    return db_path, session_id


def _tower(db_path: Path, session_id: str) -> TruthTower:
    return TruthTower(db_path, session_id)


def _seed_memory_record(db_path: Path, record_id: str, chunk_id: str = "") -> str:
    """Insert a minimal FK chain: source → document → chunk → memory_record."""
    now = int(time.time())
    chunk_id = chunk_id or f"chk_{record_id}"
    src_id = f"src_{record_id}"
    doc_id = f"doc_{record_id}"
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
            (chunk_id, doc_id, src_id, "", 0, 0, "test content", "hc0", 5, "fixed", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO memory_records "
            "(record_id, record_type, source_id, document_id, chunk_id, "
            " content, content_hash, token_estimate, lifecycle_state, "
            " created_at, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (record_id, "source_chunk", src_id, doc_id, chunk_id,
             "test content", "hr0", 5, "active", now, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return record_id


def _seed_retrieval_trace(db_path: Path, trace_id: str = "trace_test") -> str:
    """Insert a minimal retrieval_trace row so FK constraint is satisfied."""
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
    """Minimal MemoryItem stand-in that matches the fields promote_to_t1 reads."""

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


def _make_mi(
    record_id: str,
    chunk_id: str = "",
    score: float = 0.70,
    sku_address: str | None = None,
) -> _FakeMemoryItem:
    return _FakeMemoryItem(
        record_id=record_id,
        source_id=f"src_{record_id}",
        chunk_id=chunk_id or f"chk_{record_id}",
        content_excerpt=f"content for {record_id}",
        source_path=f"/test/{record_id}.md",
        sku_address=sku_address,
        score=score,
        score_components={},
        retrieval_path="sku",
        rank=0,
    )


def _make_wm_item(
    db_path: Path,
    session_id: str,
    slot_type: str = "evidence",
    salience: float = 0.60,
    record_id: str | None = None,
) -> WorkingMemoryItem:
    wm = WorkingMemory(db_path, session_id)
    return wm.promote(slot_type, record_id, f"wm content for {slot_type}", salience_score=salience)


def _count_events(db_path: Path, event_type: str) -> int:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM inspector_events WHERE event_type = ?",
            (event_type,),
        ).fetchone()[0]
    finally:
        conn.close()


def _get_event_log(db_path: Path):  # type: ignore[return]
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    return SQLiteEventLog(db_path)


# ── TowerItem dataclass ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestTowerItemDataclass:
    def test_to_dict_contains_all_fields(self) -> None:
        item = TowerItem(
            tower_item_id="tti_abc",
            session_id="sess_x",
            tier=1,
            wm_item_id=None,
            record_id="rec_001",
            retrieval_trace_id="trace_1",
            content_summary="summary",
            salience_score=0.75,
            sku_address="01000000",
            t1_citation_id=None,
            is_pinned=False,
            is_stale=False,
            promoted_at=1000,
            evicted_at=None,
        )
        d = item.to_dict()
        assert d["tower_item_id"] == "tti_abc"
        assert d["tier"] == 1
        assert d["salience_score"] == 0.75
        assert d["is_stale"] is False
        assert d["evicted_at"] is None

    def test_to_dict_is_json_serialisable(self) -> None:
        import json

        item = TowerItem(
            tower_item_id="tti_abc", session_id="sess_x", tier=2,
            wm_item_id="wmi_1", record_id=None, retrieval_trace_id=None,
            content_summary="s", salience_score=0.5, sku_address=None,
            t1_citation_id="tti_t1", is_pinned=True, is_stale=False,
            promoted_at=999, evicted_at=None,
        )
        assert json.dumps(item.to_dict())


# ── promote_to_t1 ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPromoteToT1:
    def test_new_items_returned_and_persisted(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_a")
        trace = _seed_retrieval_trace(db, "trace_a")
        tower = _tower(db, sid)
        items = tower.promote_to_t1([_make_mi("rec_a")], trace)
        assert len(items) == 1
        assert items[0].tier == 1
        assert items[0].record_id == "rec_a"
        loaded = tower.load_tier(1)
        assert loaded
        assert loaded[0].tower_item_id == items[0].tower_item_id

    def test_idempotency_same_record_not_duplicated(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_b")
        trace = _seed_retrieval_trace(db, "trace_b")
        tower = _tower(db, sid)
        tower.promote_to_t1([_make_mi("rec_b")], trace)
        tower.promote_to_t1([_make_mi("rec_b")], trace)
        assert len(tower.load_tier(1)) == 1

    def test_lattice_siblings_only_first_promoted(self) -> None:
        """Two records sharing a chunk_id: only the first encountered gets into T1."""
        db, sid = _fresh_db()
        shared_chunk = "chk_shared"
        _seed_memory_record(db, "rec_primary", chunk_id=shared_chunk)
        _seed_memory_record(db, "rec_sibling", chunk_id=shared_chunk)
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        mi_a = _make_mi("rec_primary", chunk_id=shared_chunk, score=0.80)
        mi_b = _make_mi("rec_sibling", chunk_id=shared_chunk, score=0.75)
        result = tower.promote_to_t1([mi_a, mi_b], trace)
        assert len(result) == 1
        assert result[0].record_id == "rec_primary"
        assert len(tower.load_tier(1)) == 1

    def test_existing_t1_chunk_blocks_lattice_sibling(self) -> None:
        """A lattice sibling is skipped if its chunk_id is already in an active T1."""
        db, sid = _fresh_db()
        shared_chunk = "chk_exist"
        _seed_memory_record(db, "rec_first", chunk_id=shared_chunk)
        _seed_memory_record(db, "rec_second", chunk_id=shared_chunk)
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        tower.promote_to_t1([_make_mi("rec_first", chunk_id=shared_chunk)], trace)
        result = tower.promote_to_t1([_make_mi("rec_second", chunk_id=shared_chunk)], trace)
        assert result == []
        assert len(tower.load_tier(1)) == 1

    def test_at_capacity_evicts_lowest_salience(self) -> None:
        db, sid = _fresh_db()
        cap = TOWER_CAPACITIES[1]  # 10
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        # Fill to capacity with descending salience scores
        for i in range(cap):
            rid = f"rec_{i:02d}"
            _seed_memory_record(db, rid)
            tower.promote_to_t1([_make_mi(rid, score=float(cap - i) / 10)], trace)

        # Item with score 0.1 (rec_09) should be the lowest
        assert len(tower.load_tier(1)) == cap

        # Push one more — should evict the lowest
        _seed_memory_record(db, "rec_new")
        result = tower.promote_to_t1([_make_mi("rec_new", score=0.85)], trace)
        assert len(result) == 1
        active = tower.load_tier(1)
        assert len(active) == cap
        assert all(i.record_id != "rec_09" for i in active), "lowest-salience item should have been evicted"

    def test_tower_initialized_emitted_only_on_first_t1(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_x")
        _seed_memory_record(db, "rec_y")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        el = _get_event_log(db)

        tower.promote_to_t1([_make_mi("rec_x")], trace, event_log=el)
        tower.promote_to_t1([_make_mi("rec_y")], trace, event_log=el)

        assert _count_events(db, "TowerInitialized") == 1

    def test_tower_item_promoted_event_per_item(self) -> None:
        db, sid = _fresh_db()
        for rid in ("rec_p", "rec_q"):
            _seed_memory_record(db, rid)
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        el = _get_event_log(db)
        tower.promote_to_t1([_make_mi("rec_p"), _make_mi("rec_q")], trace, event_log=el)
        assert _count_events(db, "TowerItemPromoted") == 2

    def test_empty_input_returns_empty_list(self) -> None:
        db, sid = _fresh_db()
        tower = _tower(db, sid)
        assert tower.promote_to_t1([], "trace_x") == []


# ── promote_to_t2 ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPromoteToT2:
    def _setup_with_t1(self, db: Path, sid: str) -> TowerItem:
        _seed_memory_record(db, "rec_t1")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        items = tower.promote_to_t1([_make_mi("rec_t1", score=0.70)], trace)
        return items[0]

    def test_happy_path_creates_t2_row(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        wm_item = _make_wm_item(db, sid)
        tower = _tower(db, sid)
        t2 = tower.promote_to_t2(wm_item, t1.tower_item_id)
        assert t2.tier == 2
        assert t2.t1_citation_id == t1.tower_item_id
        assert t2.session_id == sid
        assert len(tower.load_tier(2)) == 1

    def test_rejects_nonexistent_t1(self) -> None:
        db, sid = _fresh_db()
        wm_item = _make_wm_item(db, sid)
        tower = _tower(db, sid)
        with pytest.raises(TowerPromotionError, match="does not exist"):
            tower.promote_to_t2(wm_item, "tti_doesnotexist")

    def test_rejects_wrong_session_t1(self) -> None:
        db, sid = _fresh_db()
        sid2 = new_session(db, vault_path=str(db.parent))
        # Create T1 in session 2
        _seed_memory_record(db, "rec_s2")
        trace = _seed_retrieval_trace(db, "trace_s2")
        tower2 = _tower(db, sid2)
        t1_s2 = tower2.promote_to_t1([_make_mi("rec_s2")], trace)[0]
        # Attempt to cite from session 1
        wm_item = _make_wm_item(db, sid)
        tower1 = _tower(db, sid)
        with pytest.raises(TowerPromotionError, match="session"):
            tower1.promote_to_t2(wm_item, t1_s2.tower_item_id)

    def test_rejects_tier2_as_citation_target(self) -> None:
        """Citing a T2 item (not T1) as the t1_citation_id must fail."""
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        tower = _tower(db, sid)
        wm_a = _make_wm_item(db, sid, slot_type="evidence")
        t2_a = tower.promote_to_t2(wm_a, t1.tower_item_id)
        wm_b = _make_wm_item(db, sid, slot_type="context")
        with pytest.raises(TowerPromotionError, match="tier=2"):
            tower.promote_to_t2(wm_b, t2_a.tower_item_id)

    def test_rejects_evicted_t1_born_stale(self) -> None:
        """Citing an evicted T1 must raise with a clear 'evicted at' message."""
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        tower = _tower(db, sid)
        tower.evict(t1.tower_item_id, reason="test")
        wm_item = _make_wm_item(db, sid)
        with pytest.raises(TowerPromotionError, match="evicted at"):
            tower.promote_to_t2(wm_item, t1.tower_item_id)

    def test_at_capacity_evicts_lowest_salience_t2(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        cap = TOWER_CAPACITIES[2]  # 5
        tower = _tower(db, sid)
        for i in range(cap):
            wm = _make_wm_item(db, sid, slot_type="context", salience=float(cap - i) / 10)
            tower.promote_to_t2(wm, t1.tower_item_id)
        assert len(tower.load_tier(2)) == cap
        wm_new = _make_wm_item(db, sid, slot_type="hypothesis", salience=0.95)
        tower.promote_to_t2(wm_new, t1.tower_item_id)
        active_t2 = tower.load_tier(2)
        assert len(active_t2) == cap

    def test_cross_reference_event_emitted(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        wm_item = _make_wm_item(db, sid)
        tower = _tower(db, sid)
        el = _get_event_log(db)
        tower.promote_to_t2(wm_item, t1.tower_item_id, event_log=el)
        assert _count_events(db, "TowerCrossReferenceAdded") == 1

    def test_tower_item_promoted_event_emitted_for_t2(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        wm_item = _make_wm_item(db, sid)
        tower = _tower(db, sid)
        el = _get_event_log(db)
        tower.promote_to_t2(wm_item, t1.tower_item_id, event_log=el)
        # TowerItemPromoted fires for both T1 (from setup) and T2 if same el — recount
        events = connect(db).execute(
            "SELECT data_json FROM inspector_events WHERE event_type = 'TowerItemPromoted'"
        ).fetchall()
        connect(db).close()
        import json
        t2_events = [e for e in events if json.loads(e[0]).get("tier") == 2]
        assert len(t2_events) == 1

    def test_pinned_t2_not_evicted_at_capacity(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_with_t1(db, sid)
        cap = TOWER_CAPACITIES[2]
        tower = _tower(db, sid)
        wm_pinned = _make_wm_item(db, sid, slot_type="goal", salience=0.1)
        pinned_t2 = tower.promote_to_t2(wm_pinned, t1.tower_item_id, is_pinned=True)
        for i in range(cap - 1):
            wm = _make_wm_item(db, sid, slot_type="context", salience=0.5 + i * 0.01)
            tower.promote_to_t2(wm, t1.tower_item_id)
        assert len(tower.load_tier(2)) == cap
        wm_extra = _make_wm_item(db, sid, slot_type="hypothesis", salience=0.9)
        tower.promote_to_t2(wm_extra, t1.tower_item_id)
        active_ids = {i.tower_item_id for i in tower.load_tier(2)}
        assert pinned_t2.tower_item_id in active_ids


# ── evict() ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEvict:
    def _setup_t1(self, db: Path, sid: str, rid: str = "rec_ev") -> TowerItem:
        _seed_memory_record(db, rid)
        trace = _seed_retrieval_trace(db, f"trace_{rid}")
        tower = _tower(db, sid)
        return tower.promote_to_t1([_make_mi(rid)], trace)[0]

    def test_t1_eviction_marks_evicted_at(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_t1(db, sid)
        _tower(db, sid).evict(t1.tower_item_id, reason="test")
        assert _tower(db, sid).load_tier(1) == []

    def test_t1_eviction_triggers_stale_cascade(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_t1(db, sid)
        tower = _tower(db, sid)
        wm_a = _make_wm_item(db, sid)
        wm_b = _make_wm_item(db, sid, slot_type="context")
        tower.promote_to_t2(wm_a, t1.tower_item_id)
        tower.promote_to_t2(wm_b, t1.tower_item_id)
        tower.evict(t1.tower_item_id, reason="test")
        active_t2 = tower.load_tier(2)
        assert all(i.is_stale for i in active_t2)

    def test_t1_eviction_with_no_t2_citations_returns_zero(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_t1(db, sid)
        tower = _tower(db, sid)
        stale_count = tower.mark_stale_from_t1_eviction(t1.tower_item_id)
        assert stale_count == 0

    def test_t1_eviction_with_multiple_t2_stales_all(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_t1(db, sid)
        tower = _tower(db, sid)
        for _ in range(3):
            wm = _make_wm_item(db, sid, slot_type="context", salience=0.5)
            tower.promote_to_t2(wm, t1.tower_item_id)
        count = tower.mark_stale_from_t1_eviction(t1.tower_item_id)
        assert count == 3

    def test_t2_eviction_does_not_stale_others(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_t1(db, sid)
        tower = _tower(db, sid)
        wm_a = _make_wm_item(db, sid)
        wm_b = _make_wm_item(db, sid, slot_type="context")
        t2_a = tower.promote_to_t2(wm_a, t1.tower_item_id)
        tower.promote_to_t2(wm_b, t1.tower_item_id)
        tower.evict(t2_a.tower_item_id, reason="test")
        active_t2 = tower.load_tier(2)
        assert len(active_t2) == 1
        assert not active_t2[0].is_stale

    def test_evict_missing_item_raises_valueerror(self) -> None:
        db, sid = _fresh_db()
        tower = _tower(db, sid)
        with pytest.raises(ValueError, match="not found"):
            tower.evict("tti_doesnotexist", reason="test")

    def test_tower_item_evicted_event_emitted(self) -> None:
        db, sid = _fresh_db()
        t1 = self._setup_t1(db, sid)
        tower = _tower(db, sid)
        el = _get_event_log(db)
        tower.evict(t1.tower_item_id, reason="explicit", event_log=el)
        assert _count_events(db, "TowerItemEvicted") >= 1


# ── mark_stale_from_t1_eviction() ────────────────────────────────────────────


@pytest.mark.unit
class TestMarkStale:
    def test_idempotent_already_stale_not_re_emitted(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_s")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        t1 = tower.promote_to_t1([_make_mi("rec_s")], trace)[0]
        wm = _make_wm_item(db, sid)
        tower.promote_to_t2(wm, t1.tower_item_id)
        el = _get_event_log(db)

        count1 = tower.mark_stale_from_t1_eviction(t1.tower_item_id, event_log=el)
        count2 = tower.mark_stale_from_t1_eviction(t1.tower_item_id, event_log=el)

        assert count1 == 1
        assert count2 == 0  # already stale — not re-emitted
        assert _count_events(db, "TowerItemStaled") == 1  # exactly one

    def test_staled_event_emitted_per_item(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_ms")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        t1 = tower.promote_to_t1([_make_mi("rec_ms")], trace)[0]
        for _ in range(3):
            wm = _make_wm_item(db, sid, slot_type="context", salience=0.5)
            tower.promote_to_t2(wm, t1.tower_item_id)
        el = _get_event_log(db)
        count = tower.mark_stale_from_t1_eviction(t1.tower_item_id, event_log=el)
        assert count == 3
        assert _count_events(db, "TowerItemStaled") == 3


# ── load_tier() ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLoadTier:
    def test_load_tier_active_only(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_la")
        _seed_memory_record(db, "rec_lb")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        items = tower.promote_to_t1([_make_mi("rec_la"), _make_mi("rec_lb")], trace)
        tower.evict(items[0].tower_item_id, reason="test")
        active = tower.load_tier(1)
        assert len(active) == 1
        assert active[0].tower_item_id == items[1].tower_item_id

    def test_load_tier_empty_returns_empty_list(self) -> None:
        db, sid = _fresh_db()
        assert _tower(db, sid).load_tier(1) == []
        assert _tower(db, sid).load_tier(2) == []


# ── render_chronological() ────────────────────────────────────────────────────


@pytest.mark.unit
class TestRenderChronological:
    def test_renders_t1_items(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_r1")
        _seed_memory_record(db, "rec_r2")
        _seed_memory_record(db, "rec_r3")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        tower.promote_to_t1(
            [_make_mi("rec_r1"), _make_mi("rec_r2"), _make_mi("rec_r3")],
            trace,
        )
        rendered = tower.render_chronological()
        assert "T1 [1]" in rendered
        assert "T1 [2]" in rendered
        assert "T1 [3]" in rendered

    def test_t2_nested_after_cited_t1(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_nest")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        t1 = tower.promote_to_t1([_make_mi("rec_nest")], trace)[0]
        wm = _make_wm_item(db, sid)
        tower.promote_to_t2(wm, t1.tower_item_id)
        rendered = tower.render_chronological()
        assert "T1 [1]" in rendered
        assert "T2 [1] ^T1[1]" in rendered
        # T2 line must follow T1 line
        t1_pos = rendered.index("T1 [1]")
        t2_pos = rendered.index("T2 [1]")
        assert t2_pos > t1_pos

    def test_stale_t2_marked(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_stale_r")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        t1 = tower.promote_to_t1([_make_mi("rec_stale_r")], trace)[0]
        wm = _make_wm_item(db, sid)
        tower.promote_to_t2(wm, t1.tower_item_id)
        tower.mark_stale_from_t1_eviction(t1.tower_item_id)
        rendered = tower.render_chronological()
        assert "[stale]" in rendered

    def test_render_emits_tower_rendered_event(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_ev_r")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        tower.promote_to_t1([_make_mi("rec_ev_r")], trace)
        el = _get_event_log(db)
        tower.render_chronological(event_log=el)
        assert _count_events(db, "TowerRendered") == 1

    def test_empty_tower_renders_empty_string(self) -> None:
        db, sid = _fresh_db()
        assert _tower(db, sid).render_chronological() == ""


# ── to_tower_field() ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestToTowerField:
    def test_returns_none_when_empty(self) -> None:
        db, sid = _fresh_db()
        assert _tower(db, sid).to_tower_field() is None

    def test_returns_dict_with_correct_shape(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_tf")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        t1 = tower.promote_to_t1([_make_mi("rec_tf")], trace)[0]
        wm = _make_wm_item(db, sid)
        tower.promote_to_t2(wm, t1.tower_item_id)
        field = tower.to_tower_field()
        assert field is not None
        assert "t1_items" in field
        assert "t2_items" in field
        assert field["t1_count"] == 1
        assert field["t2_count"] == 1
        assert field["stale_count"] == 0

    def test_stale_count_reflects_staled_t2(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_stale_tf")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        t1 = tower.promote_to_t1([_make_mi("rec_stale_tf")], trace)[0]
        wm = _make_wm_item(db, sid)
        tower.promote_to_t2(wm, t1.tower_item_id)
        tower.mark_stale_from_t1_eviction(t1.tower_item_id)
        field = tower.to_tower_field()
        assert field is not None
        assert field["stale_count"] == 1

    def test_tower_rendered_event_emitted(self) -> None:
        db, sid = _fresh_db()
        _seed_memory_record(db, "rec_tf_ev")
        trace = _seed_retrieval_trace(db)
        tower = _tower(db, sid)
        tower.promote_to_t1([_make_mi("rec_tf_ev")], trace)
        el = _get_event_log(db)
        tower.to_tower_field(event_log=el)
        assert _count_events(db, "TowerRendered") == 1
