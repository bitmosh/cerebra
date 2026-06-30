"""
Phase 5 Step 1 tests: Migration009 schema, _constants, and event vocabulary.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cerebra.cognition._constants import (
    SLOT_CAPACITIES,
    SLOT_CAPACITY_TOTAL,
    SYNTHETIC_ITEM_DEFAULT_SALIENCE,
    TOWER_CAPACITIES,
)
from cerebra.inspector.event import (
    ALL_KNOWN_EVENT_TYPES,
    LATTICE_EVENT_TYPES,
    PHASE_0_EVENT_TYPES,
    PHASE_5_EVENT_TYPES,
    PHASE_6_EVENT_TYPES,
)
from cerebra.storage.migrations import ALL_MIGRATIONS, run_migrations

# ── helpers ──────────────────────────────────────────────────────────────────


def _fresh_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


def _migrated_db() -> Path:
    db = _fresh_db()
    run_migrations(db)
    return db


# ── constants ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestConstants:
    def test_slot_capacities_has_ten_slots(self) -> None:
        assert len(SLOT_CAPACITIES) == 10

    def test_slot_capacity_total_is_34(self) -> None:
        assert SLOT_CAPACITY_TOTAL == 34
        assert sum(SLOT_CAPACITIES.values()) == 34

    def test_slot_names_match_schema_check(self) -> None:
        expected = {
            "goal", "constraint", "context", "hypothesis", "evidence",
            "contradiction", "recent_output", "question", "procedure", "interrupt",
        }
        assert set(SLOT_CAPACITIES.keys()) == expected

    def test_individual_slot_values(self) -> None:
        assert SLOT_CAPACITIES["goal"] == 1
        assert SLOT_CAPACITIES["constraint"] == 4
        assert SLOT_CAPACITIES["context"] == 7
        assert SLOT_CAPACITIES["hypothesis"] == 3
        assert SLOT_CAPACITIES["evidence"] == 5
        assert SLOT_CAPACITIES["contradiction"] == 2
        assert SLOT_CAPACITIES["recent_output"] == 2
        assert SLOT_CAPACITIES["question"] == 3
        assert SLOT_CAPACITIES["procedure"] == 4
        assert SLOT_CAPACITIES["interrupt"] == 3

    def test_tower_capacities(self) -> None:
        assert TOWER_CAPACITIES[1] == 10
        assert TOWER_CAPACITIES[2] == 5

    def test_synthetic_salience_default(self) -> None:
        assert pytest.approx(0.8) == SYNTHETIC_ITEM_DEFAULT_SALIENCE


# ── event vocabulary ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPhase5EventTypes:
    def test_phase5_frozenset_is_frozenset(self) -> None:
        assert isinstance(PHASE_5_EVENT_TYPES, frozenset)

    def test_phase5_has_16_types(self) -> None:
        assert len(PHASE_5_EVENT_TYPES) == 16

    def test_all_known_is_union(self) -> None:
        assert ALL_KNOWN_EVENT_TYPES == (
            PHASE_0_EVENT_TYPES | PHASE_5_EVENT_TYPES | LATTICE_EVENT_TYPES | PHASE_6_EVENT_TYPES
        )

    def test_wm_events_present(self) -> None:
        for name in (
            "WorkingMemoryCreated", "AttentionItemProposed", "AttentionItemPromoted",
            "AttentionItemEvicted", "AttentionItemDeferred", "InterruptCandidateCreated",
            "WorkingMemoryRendered", "WorkingMemoryCleared",
        ):
            assert name in PHASE_5_EVENT_TYPES, name

    def test_tower_events_present(self) -> None:
        for name in (
            "TowerInitialized", "TowerItemPromoted", "TowerItemEvicted",
            "TowerCrossReferenceAdded", "TowerItemStaled", "TowerTierRebuilt",
            "TowerCollapsed", "TowerRendered",
        ):
            assert name in PHASE_5_EVENT_TYPES, name

    def test_no_overlap_with_phase0(self) -> None:
        overlap = PHASE_0_EVENT_TYPES & PHASE_5_EVENT_TYPES
        assert overlap == frozenset(), f"Overlap found: {overlap}"


# ── Migration009 table structure ──────────────────────────────────────────────


@pytest.mark.unit
class TestMigration009:
    def test_migration009_creates_three_tables(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "sessions" in tables
            assert "working_memory_items" in tables
            assert "truth_tower_items" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration009_is_idempotent(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            second = run_migrations(db)
            assert 9 not in second
        finally:
            db.unlink(missing_ok=True)

    def test_migration009_in_all_migrations(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert 9 in versions

    def test_sessions_status_check_constraint(self) -> None:
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            # Valid insert
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, status, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 'active', 1, 1)"
            )
            conn.commit()
            # Invalid status
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO sessions (session_id, vault_path, status, started_at, last_active_at) "
                    "VALUES ('sess_002', '/vault', 'invalid', 1, 1)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_wmi_slot_type_check_constraint(self) -> None:
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            conn.commit()
            # Valid slot
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, content_summary, promoted_at) "
                "VALUES ('wmi_001', 'sess_001', 'goal', 'test goal', 1)"
            )
            conn.commit()
            # Invalid slot
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO working_memory_items "
                    "(item_id, session_id, slot_type, content_summary, promoted_at) "
                    "VALUES ('wmi_002', 'sess_001', 'unknown_slot', 'bad', 1)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_wmi_fk_to_sessions_restricts(self) -> None:
        """working_memory_items must reject inserts with unknown session_id."""
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO working_memory_items "
                    "(item_id, session_id, slot_type, content_summary, promoted_at) "
                    "VALUES ('wmi_001', 'nonexistent_session', 'goal', 'test', 1)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_wmi_on_delete_restrict_blocks_session_delete(self) -> None:
        """Cannot delete a session while working_memory_items reference it."""
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, content_summary, promoted_at) "
                "VALUES ('wmi_001', 'sess_001', 'goal', 'test goal', 1)"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM sessions WHERE session_id='sess_001'")
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_tti_tier_check_constraint(self) -> None:
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            conn.commit()
            # Valid T1 insert (t1_citation_id NULL)
            conn.execute(
                "INSERT INTO truth_tower_items "
                "(tower_item_id, session_id, tier, content_summary, salience_score, promoted_at) "
                "VALUES ('tti_001', 'sess_001', 1, 'evidence', 0.8, 1)"
            )
            conn.commit()
            # Invalid tier
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO truth_tower_items "
                    "(tower_item_id, session_id, tier, content_summary, salience_score, promoted_at) "
                    "VALUES ('tti_bad', 'sess_001', 3, 'bad', 0.5, 1)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_tti_tier_citation_check_constraint(self) -> None:
        """T1 must have t1_citation_id=NULL; T2 must have t1_citation_id NOT NULL."""
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            conn.commit()
            # T1 with non-NULL t1_citation_id — should fail CHECK
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO truth_tower_items "
                    "(tower_item_id, session_id, tier, content_summary, "
                    " salience_score, t1_citation_id, promoted_at) "
                    "VALUES ('tti_bad', 'sess_001', 1, 'bad', 0.5, 'tti_something', 1)"
                )
            conn.commit()
            # T2 with NULL t1_citation_id — should fail CHECK
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO truth_tower_items "
                    "(tower_item_id, session_id, tier, content_summary, "
                    " salience_score, t1_citation_id, promoted_at) "
                    "VALUES ('tti_bad2', 'sess_001', 2, 'bad', 0.5, NULL, 1)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_tti_fk_to_sessions_restricts(self) -> None:
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO truth_tower_items "
                    "(tower_item_id, session_id, tier, content_summary, salience_score, promoted_at) "
                    "VALUES ('tti_001', 'no_such_session', 1, 'test', 0.5, 1)"
                )
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_tti_on_delete_restrict_blocks_session_delete(self) -> None:
        """Cannot delete a session while truth_tower_items reference it."""
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            conn.execute(
                "INSERT INTO truth_tower_items "
                "(tower_item_id, session_id, tier, content_summary, salience_score, promoted_at) "
                "VALUES ('tti_001', 'sess_001', 1, 'evidence', 0.8, 1)"
            )
            conn.commit()
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM sessions WHERE session_id='sess_001'")
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_tti_t2_self_citation_roundtrip(self) -> None:
        """T2 item citing a T1 item in the same table inserts and queries correctly."""
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            # T1 item
            conn.execute(
                "INSERT INTO truth_tower_items "
                "(tower_item_id, session_id, tier, content_summary, salience_score, promoted_at) "
                "VALUES ('tti_t1', 'sess_001', 1, 'T1 evidence', 0.7, 1)"
            )
            # T2 item citing T1
            conn.execute(
                "INSERT INTO truth_tower_items "
                "(tower_item_id, session_id, tier, content_summary, "
                " salience_score, t1_citation_id, promoted_at) "
                "VALUES ('tti_t2', 'sess_001', 2, 'T2 interpretation', 0.6, 'tti_t1', 2)"
            )
            conn.commit()
            row = conn.execute(
                "SELECT tier, t1_citation_id FROM truth_tower_items WHERE tower_item_id='tti_t2'"
            ).fetchone()
            assert row[0] == 2
            assert row[1] == "tti_t1"
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_forward_compat_columns_nullable(self) -> None:
        """interpretive_lens and frame_metadata_json accept NULL."""
        db = _migrated_db()
        try:
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO sessions (session_id, vault_path, started_at, last_active_at) "
                "VALUES ('sess_001', '/vault', 1, 1)"
            )
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, content_summary, promoted_at, "
                " interpretive_lens, frame_metadata_json) "
                "VALUES ('wmi_001', 'sess_001', 'context', 'test', 1, NULL, NULL)"
            )
            conn.commit()
            row = conn.execute(
                "SELECT interpretive_lens, frame_metadata_json FROM working_memory_items "
                "WHERE item_id='wmi_001'"
            ).fetchone()
            assert row[0] is None
            assert row[1] is None
            conn.close()
        finally:
            db.unlink(missing_ok=True)
