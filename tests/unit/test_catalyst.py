"""Unit tests for cerebra.cognition.catalyst — Phase 9 Step 3."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from cerebra.cognition.catalyst import CatalystEngine
from cerebra.cognition.cycle_config import CatalystArm
from cerebra.storage.migrations import run_migrations


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _migrated_db() -> Path:
    """Return path to a fresh temp DB with all migrations applied."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = Path(tmp.name)
    run_migrations(path)
    return path


def _seed_session(db_path: Path, session_id: str) -> None:
    """Insert a minimal runtime_sessions row so FK constraints pass."""
    import time

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO runtime_sessions "
            "(session_id, cycle_config, goal, vault_path, opened_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, "test.v0", "test goal", "/tmp/vault", int(time.time() * 1000)),
        )
        conn.commit()
    finally:
        conn.close()


def _make_arms(names: list[str], arm_type: str = "verification") -> list[CatalystArm]:
    return [
        CatalystArm(
            arm_id=name,
            type=arm_type,
            mapped_action="refine",
            strategy_prompt=f"Strategy: {name}.",
        )
        for name in names
    ]


def _make_mixed_arms() -> list[CatalystArm]:
    """5 arms with mixed types matching planning.adaptive.v0 vocabulary."""
    return [
        CatalystArm("constraint_check", "verification", "refine", "Check constraints."),
        CatalystArm("decomposition", "structuring", "refine", "Decompose sub-goals."),
        CatalystArm("risk_assessment", "verification", "refine", "Assess risks."),
        CatalystArm("prerequisite_id", "structuring", "refine", "Identify prerequisites."),
        CatalystArm("resource_estimate", "estimation", "refine", "Estimate resources."),
    ]


# ── TestCatalystEngineInit ─────────────────────────────────────────────────────


class TestCatalystEngineInit:
    def test_no_arms_engine_initializes(self) -> None:
        db = _migrated_db()
        engine = CatalystEngine("sess_001", db, [])
        assert engine._arms == []

    def test_with_arms_bandit_has_correct_arm_ids(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_002")
        arms = _make_arms(["alpha", "beta", "gamma"])
        engine = CatalystEngine("sess_002", db, arms)
        assert set(engine._bandit.arms.keys()) == {"alpha", "beta", "gamma"}

    def test_arm_map_populated(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_003")
        arms = _make_arms(["x", "y"])
        engine = CatalystEngine("sess_003", db, arms)
        assert "x" in engine._arm_map
        assert "y" in engine._arm_map


# ── TestSelectNoArms ──────────────────────────────────────────────────────────


class TestSelectNoArms:
    def test_no_arms_returns_none(self) -> None:
        db = _migrated_db()
        engine = CatalystEngine("sess_empty", db, [])
        assert engine.select() is None


# ── TestForcedExploration ─────────────────────────────────────────────────────


class TestForcedExploration:
    def test_first_select_is_forced_exploration(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_fe1")
        arms = _make_arms(["arm_a", "arm_b", "arm_c"])
        engine = CatalystEngine("sess_fe1", db, arms)
        sel = engine.select()
        assert sel is not None
        assert sel.selection_reason == "forced_exploration"
        assert sel.arm_id == "arm_a"  # first by declaration order

    def test_forced_exploration_cycles_through_all_arms(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_fe2")
        arms = _make_arms(["a", "b", "c"])
        engine = CatalystEngine("sess_fe2", db, arms)
        seen = []
        for _ in range(3):
            sel = engine.select()
            assert sel is not None
            assert sel.selection_reason == "forced_exploration"
            seen.append(sel.arm_id)
            engine.record_reward(sel.arm_id, 0.5, step_index=len(seen))
        assert seen == ["a", "b", "c"]

    def test_after_all_arms_explored_uses_scoring(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_fe3")
        arms = _make_arms(["a", "b"])
        engine = CatalystEngine("sess_fe3", db, arms)
        engine.record_reward("a", 0.8, step_index=1)
        engine.record_reward("b", 0.4, step_index=2)
        sel = engine.select()
        assert sel is not None
        assert sel.selection_reason == "scored"


# ── TestScoredSelection ────────────────────────────────────────────────────────


class TestScoredSelection:
    def test_higher_reward_arm_scores_higher(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_score1")
        arms = _make_arms(["low", "high"])
        engine = CatalystEngine("sess_score1", db, arms)
        engine.record_reward("low", 0.2, step_index=1)
        engine.record_reward("high", 0.9, step_index=2)
        sel = engine.select()
        assert sel is not None
        assert sel.arm_id == "high"

    def test_score_components_present(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_score2")
        arms = _make_arms(["a", "b"])
        engine = CatalystEngine("sess_score2", db, arms)
        engine.record_reward("a", 0.6, step_index=1)
        engine.record_reward("b", 0.7, step_index=2)
        sel = engine.select()
        assert sel is not None
        assert "base_reward" in sel.score_components
        assert "type_penalty" in sel.score_components
        assert "confidence_ramp" in sel.score_components

    def test_type_penalty_discounts_recent_same_type(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_score3")
        # Two verification arms + one estimation arm
        arms = [
            CatalystArm("v1", "verification", "refine", "v1 strategy"),
            CatalystArm("v2", "verification", "refine", "v2 strategy"),
            CatalystArm("e1", "estimation", "refine", "e1 strategy"),
        ]
        engine = CatalystEngine("sess_score3", db, arms)
        # Seed all with same reward so only type_penalty differentiates
        engine.record_reward("v1", 0.7, step_index=1)
        engine.record_reward("v2", 0.7, step_index=2)
        engine.record_reward("e1", 0.7, step_index=3)
        # Simulate recent selection of v1 (verification type)
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "INSERT INTO catalyst_recent_selections "
                "(runtime_session_id, selection_order, arm_id, arm_type, selected_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("sess_score3", 10, "v1", "verification", 1000),
            )
            conn.commit()
        finally:
            conn.close()
        sel = engine.select()
        assert sel is not None
        # estimation type should be preferred (not penalized by verification recency)
        assert sel.arm_id == "e1"

    def test_confidence_ramp_increases_with_count(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_score4")
        arms = _make_arms(["a", "b"])
        engine = CatalystEngine("sess_score4", db, arms)
        # a: count=1 (low confidence), b: count=5 (full confidence)
        engine.record_reward("a", 0.9, step_index=1)
        for i in range(2, 7):
            engine.record_reward("b", 0.5, step_index=i)
        # b has mean_reward=0.5, confidence_ramp=1.0 → score=0.5
        # a has mean_reward=0.9, confidence_ramp=0.2 → score=0.18
        sel = engine.select()
        assert sel is not None
        assert sel.arm_id == "b"


# ── TestRecordReward ──────────────────────────────────────────────────────────


class TestRecordReward:
    def test_record_reward_updates_bandit_count(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_rr1")
        arms = _make_arms(["arm"])
        engine = CatalystEngine("sess_rr1", db, arms)
        engine.record_reward("arm", 0.6, step_index=1)
        stats = engine._bandit.get_stats("arm")
        assert stats.count == 1
        assert abs(stats.total_reward - 0.6) < 1e-9

    def test_record_reward_persists_to_db(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_rr2")
        arms = _make_arms(["arm"])
        engine = CatalystEngine("sess_rr2", db, arms)
        engine.record_reward("arm", 0.75, step_index=2)
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT count, total_reward FROM catalyst_arm_stats "
                "WHERE arm_id = ? AND runtime_session_id = ?",
                ("arm", "sess_rr2"),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == 1
        assert abs(row[1] - 0.75) < 1e-9

    def test_record_reward_unknown_arm_is_noop(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_rr3")
        arms = _make_arms(["known"])
        engine = CatalystEngine("sess_rr3", db, arms)
        engine.record_reward("unknown_arm", 0.9, step_index=1)
        stats = engine._bandit.get_stats("known")
        assert stats.count == 0  # known arm untouched

    def test_multiple_rewards_accumulate(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_rr4")
        arms = _make_arms(["arm"])
        engine = CatalystEngine("sess_rr4", db, arms)
        engine.record_reward("arm", 0.4, step_index=1)
        engine.record_reward("arm", 0.6, step_index=2)
        stats = engine._bandit.get_stats("arm")
        assert stats.count == 2
        assert abs(stats.mean_reward - 0.5) < 1e-9


# ── TestRecentSelectionTracking ───────────────────────────────────────────────


class TestRecentSelectionTracking:
    def test_recent_selections_recorded(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_rs1")
        arms = _make_arms(["a", "b"])
        engine = CatalystEngine("sess_rs1", db, arms)
        engine.record_reward("a", 0.5, step_index=1)
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT arm_id FROM catalyst_recent_selections WHERE runtime_session_id = ?",
                ("sess_rs1",),
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "a"

    def test_recent_types_window_is_k_5(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_rs2")
        arms = _make_mixed_arms()
        engine = CatalystEngine("sess_rs2", db, arms)
        # Record 7 rewards — window should return only last 5
        for i, arm in enumerate(arms):
            engine.record_reward(arm.arm_id, 0.5, step_index=i + 1)
        # Then record two more for constraint_check (verification)
        engine.record_reward("constraint_check", 0.5, step_index=6)
        engine.record_reward("constraint_check", 0.5, step_index=7)
        recent = engine._load_recent_types()
        assert len(recent) == 5  # K=5 window


# ── TestStatePersistence ──────────────────────────────────────────────────────


class TestStatePersistence:
    def test_state_survives_engine_recreation(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_pers1")
        arms = _make_arms(["arm"])

        engine1 = CatalystEngine("sess_pers1", db, arms)
        engine1.record_reward("arm", 0.8, step_index=1)

        # Recreate from same session
        engine2 = CatalystEngine("sess_pers1", db, arms)
        stats = engine2._bandit.get_stats("arm")
        assert stats.count == 1
        assert abs(stats.mean_reward - 0.8) < 1e-9


# ── TestSelectionResult ───────────────────────────────────────────────────────


class TestSelectionResult:
    def test_selection_has_strategy_prompt(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_sp1")
        arms = _make_mixed_arms()
        engine = CatalystEngine("sess_sp1", db, arms)
        sel = engine.select()
        assert sel is not None
        assert len(sel.strategy_prompt) > 0

    def test_selection_mapped_action_is_refine(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_ma1")
        arms = _make_mixed_arms()
        engine = CatalystEngine("sess_ma1", db, arms)
        sel = engine.select()
        assert sel is not None
        assert sel.mapped_action == "refine"

    def test_forced_exploration_score_is_zero(self) -> None:
        db = _migrated_db()
        _seed_session(db, "sess_fe_score")
        arms = _make_arms(["arm"])
        engine = CatalystEngine("sess_fe_score", db, arms)
        sel = engine.select()
        assert sel is not None
        assert sel.score == 0.0
