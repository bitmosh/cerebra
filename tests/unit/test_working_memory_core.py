"""Unit tests for WorkingMemory and WorkingMemoryItem (Phase 5 Step 3)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from cerebra.cognition._constants import (
    SLOT_CAPACITIES,
    SYNTHETIC_ITEM_DEFAULT_SALIENCE,
)
from cerebra.cognition.working_memory import (
    PromotionError,
    WorkingMemory,
    WorkingMemoryItem,
    new_session,
)
from cerebra.storage.db import connect
from cerebra.storage.migrations import run_migrations


# ── helpers ───────────────────────────────────────────────────────────────────


def _fresh_db() -> tuple[Path, str]:
    """Return (db_path, session_id) for a throw-away DB file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    run_migrations(db_path)
    session_id = new_session(db_path, vault_path=str(db_path.parent))
    return db_path, session_id


def _wm(db_path: Path, session_id: str) -> WorkingMemory:
    return WorkingMemory(db_path, session_id)


def _plant_tower_citation(db_path: Path, session_id: str, wm_item_id: str) -> None:
    """Insert a T1 truth_tower_items row pointing at wm_item_id."""
    conn = connect(db_path)
    try:
        tower_id = f"twr_{wm_item_id[-8:]}"
        conn.execute(
            "INSERT INTO truth_tower_items "
            "(tower_item_id, session_id, wm_item_id, tier, content_summary, "
            " salience_score, promoted_at, schema_version) "
            "VALUES (?, ?, ?, 1, 'test tower item', 0.9, ?, 1)",
            (tower_id, session_id, wm_item_id, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_memory_record(db_path: Path, record_id: str = "rec_test") -> str:
    """Seed the minimum source/document/chunk/memory_record rows for FK tests."""
    conn = connect(db_path)
    try:
        now = int(time.time())
        src_id = f"src_{record_id}"
        doc_id = f"doc_{record_id}"
        chk_id = f"chk_{record_id}"
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(source_id, canonical_path, content_hash, size_bytes, "
            " detected_type, detection_confidence, parser_status, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (src_id, f"/test/{record_id}", "h0", 1, "markdown", 1.0, "done", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO documents "
            "(document_id, source_id, document_type, normalization_confidence, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, src_id, "markdown", 1.0, "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO chunks "
            "(chunk_id, document_id, source_id, heading_path, chunk_index, "
            " depth, content, content_hash, token_estimate, chunk_strategy, "
            " lifecycle_state, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chk_id, doc_id, src_id, "", 0, 0, "content", "hc0", 5, "fixed", "active", now, 1),
        )
        conn.execute(
            "INSERT OR IGNORE INTO memory_records "
            "(record_id, record_type, source_id, document_id, chunk_id, "
            " content, content_hash, token_estimate, lifecycle_state, "
            " created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, "source_chunk", src_id, doc_id, chk_id,
             "content", "hr0", 5, "active", now, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return record_id


# ── WorkingMemoryItem dataclass ───────────────────────────────────────────────


@pytest.mark.unit
class TestWorkingMemoryItemDataclass:
    def test_fields_present(self) -> None:
        item = WorkingMemoryItem(
            item_id="wmi_abc",
            session_id="sess_xyz",
            slot_type="goal",
            record_id=None,
            content_summary="test",
            salience_score=0.5,
            is_pinned=False,
            promoted_at=1000,
            evicted_at=None,
        )
        assert item.item_id == "wmi_abc"
        assert item.session_id == "sess_xyz"
        assert item.slot_type == "goal"
        assert item.record_id is None
        assert item.content_summary == "test"
        assert item.salience_score == 0.5
        assert item.is_pinned is False
        assert item.promoted_at == 1000
        assert item.evicted_at is None

    def test_no_is_tower_cited_field(self) -> None:
        item = WorkingMemoryItem(
            item_id="wmi_abc",
            session_id="sess_xyz",
            slot_type="goal",
            record_id=None,
            content_summary="test",
            salience_score=0.5,
            is_pinned=False,
            promoted_at=1000,
            evicted_at=None,
        )
        assert not hasattr(item, "is_tower_cited"), (
            "is_tower_cited must not be a stored field — it is computed via JOIN"
        )

    def test_to_dict_roundtrip(self) -> None:
        item = WorkingMemoryItem(
            item_id="wmi_abc",
            session_id="sess_xyz",
            slot_type="context",
            record_id="rec_001",
            content_summary="some context",
            salience_score=0.75,
            is_pinned=True,
            promoted_at=9999,
            evicted_at=None,
        )
        d = item.to_dict()
        assert d["item_id"] == "wmi_abc"
        assert d["slot_type"] == "context"
        assert d["record_id"] == "rec_001"
        assert d["salience_score"] == 0.75
        assert d["is_pinned"] is True
        assert d["evicted_at"] is None

    def test_to_dict_keys(self) -> None:
        item = WorkingMemoryItem(
            item_id="x", session_id="y", slot_type="goal",
            record_id=None, content_summary="c", salience_score=0.1,
            is_pinned=False, promoted_at=1, evicted_at=None,
        )
        keys = set(item.to_dict().keys())
        expected = {
            "item_id", "session_id", "slot_type", "record_id",
            "content_summary", "salience_score", "is_pinned",
            "promoted_at", "evicted_at",
        }
        assert keys == expected


# ── WorkingMemory.promote ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestPromote:
    def test_promote_basic_returns_item(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "achieve X", salience_score=0.7)
        assert item.slot_type == "goal"
        assert item.content_summary == "achieve X"
        assert item.salience_score == 0.7
        assert item.is_pinned is False
        assert item.evicted_at is None
        assert item.item_id.startswith("wmi_")

    def test_promote_item_id_unique(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        a = wm.promote("context", None, "ctx a", salience_score=0.5)
        b = wm.promote("context", None, "ctx b", salience_score=0.4)
        assert a.item_id != b.item_id

    def test_promote_default_salience_for_synthetic(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("question", None, "why?")
        assert item.salience_score == SYNTHETIC_ITEM_DEFAULT_SALIENCE

    def test_promote_explicit_salience_overrides_default(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("question", None, "why?", salience_score=0.33)
        assert item.salience_score == 0.33

    def test_promote_with_record_id(self) -> None:
        db_path, session_id = _fresh_db()
        record_id = _seed_memory_record(db_path, "rec_123")
        wm = _wm(db_path, session_id)
        item = wm.promote("evidence", record_id, "found something", salience_score=0.6)
        assert item.record_id == "rec_123"

    def test_promote_persists_to_db(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "persist this", salience_score=0.5)
        loaded = wm.load_slot("goal")
        assert len(loaded) == 1
        assert loaded[0].item_id == item.item_id

    def test_promote_pinned_item(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "pinned goal", salience_score=0.9, is_pinned=True)
        assert item.is_pinned is True
        loaded = wm.load_slot("goal")
        assert loaded[0].is_pinned is True

    def test_promote_unknown_slot_raises(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        with pytest.raises(ValueError, match="Unknown slot_type"):
            wm.promote("nonexistent_slot", None, "bad")


# ── eviction logic ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEvictionPolicy:
    def test_evicts_lowest_salience_when_over_capacity(self) -> None:
        """contradiction capacity=2: inserting a 3rd item evicts lowest salience."""
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        a = wm.promote("contradiction", None, "contra A", salience_score=0.6)
        b = wm.promote("contradiction", None, "contra B", salience_score=0.4)  # lowest
        _c = wm.promote("contradiction", None, "contra C", salience_score=0.5)

        active = wm.load_slot("contradiction")
        ids = {i.item_id for i in active}
        assert b.item_id not in ids, "lowest-salience item must be evicted"
        assert a.item_id in ids
        assert len(active) == 2

    def test_evicted_item_has_evicted_at_set(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("contradiction", None, "contra A", salience_score=0.6)
        wm.promote("contradiction", None, "contra B", salience_score=0.4)  # to be evicted
        wm.promote("contradiction", None, "contra C", salience_score=0.5)

        # Verify via direct DB query that evicted_at is set
        conn = connect(db_path)
        try:
            rows = conn.execute(
                "SELECT item_id, evicted_at FROM working_memory_items "
                "WHERE session_id = ? AND slot_type = 'contradiction'",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        evicted = [r for r in rows if r["evicted_at"] is not None]
        assert len(evicted) == 1

    def test_pinned_item_never_evicted(self) -> None:
        """Pinned item must survive even if it has the lowest salience."""
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        # capacity=2 for contradiction
        pinned = wm.promote(
            "contradiction", None, "pinned low", salience_score=0.1, is_pinned=True
        )
        other = wm.promote("contradiction", None, "other mid", salience_score=0.5)
        # Promote a 3rd → must evict `other` (pinned is protected)
        _third = wm.promote("contradiction", None, "new high", salience_score=0.9)

        active = wm.load_slot("contradiction")
        ids = {i.item_id for i in active}
        assert pinned.item_id in ids, "pinned item must survive eviction"
        assert other.item_id not in ids

    def test_slot_full_pinned_raises_promotion_error(self) -> None:
        """When all capacity slots are pinned, PromotionError is raised."""
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        # goal capacity=1
        wm.promote("goal", None, "pinned goal", salience_score=0.9, is_pinned=True)
        with pytest.raises(PromotionError, match="pinned"):
            wm.promote("goal", None, "new goal", salience_score=0.3)

    def test_slot_full_pinned_does_not_persist_failed_item(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("goal", None, "pinned goal", salience_score=0.9, is_pinned=True)
        try:
            wm.promote("goal", None, "rejected goal", salience_score=0.3)
        except PromotionError:
            pass
        active = wm.load_slot("goal")
        assert len(active) == 1
        assert active[0].content_summary == "pinned goal"

    def test_tower_cited_item_eviction_resistant(self) -> None:
        """Tower-cited item gets +0.20 effective salience; bare-lower item evicted first."""
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        # contradiction capacity=2
        # a: salience 0.5 — bare
        # b: salience 0.4 — but tower-cited → effective 0.60
        a = wm.promote("contradiction", None, "bare mid", salience_score=0.5)
        b = wm.promote("contradiction", None, "tower low", salience_score=0.4)
        _plant_tower_citation(db_path, session_id, b.item_id)

        # Promote c: a is evicted (effective 0.50), b survives (effective 0.60)
        _c = wm.promote("contradiction", None, "new item", salience_score=0.55)

        active = wm.load_slot("contradiction")
        ids = {i.item_id for i in active}
        assert a.item_id not in ids, "bare item (lower effective salience) should be evicted"
        assert b.item_id in ids, "tower-cited item should survive"

    def test_tie_broken_by_oldest_promoted_at(self) -> None:
        """When effective salience is equal, the oldest item is evicted first."""
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        # contradiction capacity=2; insert 2 identical-salience items
        a = wm.promote("contradiction", None, "older", salience_score=0.5)
        # Ensure b.promoted_at > a.promoted_at
        time.sleep(0.01)
        b = wm.promote("contradiction", None, "newer", salience_score=0.5)
        assert b.promoted_at >= a.promoted_at

        _c = wm.promote("contradiction", None, "third", salience_score=0.5)
        active = wm.load_slot("contradiction")
        ids = {i.item_id for i in active}
        assert a.item_id not in ids, "oldest item should be evicted on tie"
        assert b.item_id in ids


# ── WorkingMemory.evict ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestExplicitEvict:
    def test_evict_sets_evicted_at(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "evict me", salience_score=0.5)
        wm.evict(item.item_id, reason="manual")
        active = wm.load_slot("goal")
        assert active == []

    def test_evict_missing_item_raises(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        with pytest.raises(ValueError, match="not found"):
            wm.evict("wmi_nonexistent", reason="manual")

    def test_evict_already_evicted_raises(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "evict once", salience_score=0.5)
        wm.evict(item.item_id, reason="first")
        with pytest.raises(ValueError, match="not found"):
            wm.evict(item.item_id, reason="second")


# ── load_slot / load_all_active ───────────────────────────────────────────────


@pytest.mark.unit
class TestLoad:
    def test_load_slot_empty(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        assert wm.load_slot("goal") == []

    def test_load_slot_returns_active_only(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        item = wm.promote("context", None, "active", salience_score=0.5)
        evicted = wm.promote("context", None, "evicted", salience_score=0.5)
        wm.evict(evicted.item_id, reason="test")
        active = wm.load_slot("context")
        ids = {i.item_id for i in active}
        assert item.item_id in ids
        assert evicted.item_id not in ids

    def test_load_slot_ordered_by_promoted_at(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        a = wm.promote("context", None, "first", salience_score=0.3)
        time.sleep(0.01)
        b = wm.promote("context", None, "second", salience_score=0.5)
        loaded = wm.load_slot("context")
        assert loaded[0].item_id == a.item_id
        assert loaded[1].item_id == b.item_id

    def test_load_all_active_has_all_10_slot_keys(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        result = wm.load_all_active()
        assert set(result.keys()) == set(SLOT_CAPACITIES.keys())

    def test_load_all_active_empty_slots_are_lists(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        result = wm.load_all_active()
        for slot_type, items in result.items():
            assert isinstance(items, list), f"slot {slot_type!r} should be a list"

    def test_load_all_active_items_bucketed_correctly(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("goal", None, "a goal", salience_score=0.5)
        wm.promote("context", None, "some ctx", salience_score=0.4)
        result = wm.load_all_active()
        assert len(result["goal"]) == 1
        assert len(result["context"]) == 1
        assert len(result["question"]) == 0

    def test_load_all_active_cross_session_isolation(self) -> None:
        """Items from another session must not appear."""
        db_path, _ = _fresh_db()
        sid_a = new_session(db_path, vault_path=str(db_path.parent))
        sid_b = new_session(db_path, vault_path=str(db_path.parent))
        wm_a = WorkingMemory(db_path, sid_a)
        wm_b = WorkingMemory(db_path, sid_b)
        wm_a.promote("goal", None, "session A goal", salience_score=0.5)
        result_b = wm_b.load_all_active()
        assert result_b["goal"] == [], "session B must not see session A items"


# ── render_text / to_dict ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestRenderAndSerialise:
    def test_render_text_empty(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        text = wm.render_text()
        assert "Working Memory" in text
        assert "empty" in text.lower()

    def test_render_text_shows_slot_type(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("hypothesis", None, "my hypothesis", salience_score=0.6)
        text = wm.render_text()
        assert "hypothesis" in text
        assert "my hypothesis" in text

    def test_render_text_shows_pinned_marker(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("goal", None, "locked goal", salience_score=0.9, is_pinned=True)
        text = wm.render_text()
        assert "pinned" in text.lower()

    def test_render_text_shows_capacity(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("evidence", None, "evidence item", salience_score=0.5)
        text = wm.render_text()
        assert "1/5" in text  # evidence capacity is 5

    def test_to_dict_session_id(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        d = wm.to_dict()
        assert d["session_id"] == session_id

    def test_to_dict_has_all_slot_keys(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        d = wm.to_dict()
        assert set(d["slots"].keys()) == set(SLOT_CAPACITIES.keys())

    def test_to_dict_item_count(self) -> None:
        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("goal", None, "item1", salience_score=0.5)
        wm.promote("context", None, "item2", salience_score=0.4)
        d = wm.to_dict()
        assert d["total_item_count"] == 2

    def test_to_dict_json_serialisable(self) -> None:
        import json

        db_path, session_id = _fresh_db()
        wm = _wm(db_path, session_id)
        wm.promote("question", None, "JSON?", salience_score=0.55)
        d = wm.to_dict()
        serialised = json.dumps(d)
        assert len(serialised) > 0


# ── event emission ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEventEmission:
    def _event_log(self, db_path: Path):  # type: ignore[return]
        from cerebra.inspector.sqlite_log import SQLiteEventLog

        return SQLiteEventLog(db_path)

    def test_promote_emits_proposed_and_promoted(self) -> None:
        db_path, session_id = _fresh_db()
        event_log = self._event_log(db_path)
        wm = _wm(db_path, session_id)
        wm.promote("goal", None, "event test", salience_score=0.5, event_log=event_log)

        conn = connect(db_path)
        try:
            types = [
                r["event_type"]
                for r in conn.execute(
                    "SELECT event_type FROM inspector_events "
                    "WHERE event_type IN ('AttentionItemProposed','AttentionItemPromoted') "
                    "ORDER BY timestamp ASC"
                ).fetchall()
            ]
        finally:
            conn.close()

        assert "AttentionItemProposed" in types
        assert "AttentionItemPromoted" in types

    def test_eviction_emits_evicted_event(self) -> None:
        db_path, session_id = _fresh_db()
        event_log = self._event_log(db_path)
        wm = _wm(db_path, session_id)
        # goal capacity=1; promote two → eviction fires
        wm.promote("goal", None, "first", salience_score=0.3, event_log=event_log)
        wm.promote("goal", None, "second", salience_score=0.7, event_log=event_log)

        conn = connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM inspector_events "
                "WHERE event_type = 'AttentionItemEvicted'"
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 1

    def test_explicit_evict_emits_evicted_event(self) -> None:
        db_path, session_id = _fresh_db()
        event_log = self._event_log(db_path)
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "item", salience_score=0.5)
        wm.evict(item.item_id, reason="test_reason", event_log=event_log)

        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT data_json FROM inspector_events "
                "WHERE event_type = 'AttentionItemEvicted' LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        import json

        assert row is not None
        payload = json.loads(row[0])
        assert payload["eviction_reason"] == "test_reason"

    def test_evicted_event_includes_was_tower_cited(self) -> None:
        db_path, session_id = _fresh_db()
        event_log = self._event_log(db_path)
        wm = _wm(db_path, session_id)
        item = wm.promote("goal", None, "item", salience_score=0.5)
        _plant_tower_citation(db_path, session_id, item.item_id)
        wm.evict(item.item_id, reason="test", event_log=event_log)

        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT data_json FROM inspector_events "
                "WHERE event_type = 'AttentionItemEvicted' LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        import json

        payload = json.loads(row[0])
        assert payload["was_tower_cited"] is True

    def test_deferred_event_emitted_on_pinned_full_slot(self) -> None:
        db_path, session_id = _fresh_db()
        event_log = self._event_log(db_path)
        wm = _wm(db_path, session_id)
        wm.promote("goal", None, "pinned", salience_score=0.9, is_pinned=True, event_log=event_log)
        try:
            wm.promote("goal", None, "blocked", salience_score=0.3, event_log=event_log)
        except PromotionError:
            pass

        conn = connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM inspector_events "
                "WHERE event_type = 'AttentionItemDeferred'"
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 1
