# SPDX-License-Identifier: Apache-2.0
"""Contract tests for all six Lattica primitives (vendored copy)."""

from __future__ import annotations

import pytest

from cerebra._primitives import (
    Clutch,
    Decision,
    HysteresisModeRouter,
    ItemState,
    Rule,
    TombstoneSet,
    TrajectoryTracker,
    compose,
    triangulate,
    triangulate_with_components,
)

# ── Clutch ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestClutch:
    def _make_clutch(self) -> Clutch:
        default = Decision(action="accept", intensity=None, reason="default", confidence=0.5)
        rules = [
            Rule(
                name="high_score",
                guard=lambda s, _st: s.get("score", 0) > 0.8,
                action=Decision(
                    action="promote", intensity="high", reason="score > 0.8", confidence=0.9
                ),
            ),
            Rule(
                name="low_score",
                guard=lambda s, _st: s.get("score", 0) < 0.3,
                action=Decision(
                    action="reject", intensity="low", reason="score < 0.3", confidence=0.8
                ),
            ),
        ]
        return Clutch(rules=rules, default=default)

    def test_first_matching_rule_wins(self) -> None:
        c = self._make_clutch()
        d = c.decide({"score": 0.9}, {})
        assert d.action == "promote"
        assert d.confidence == 0.9

    def test_second_rule_matches(self) -> None:
        c = self._make_clutch()
        d = c.decide({"score": 0.1}, {})
        assert d.action == "reject"

    def test_default_when_no_rule_matches(self) -> None:
        c = self._make_clutch()
        d = c.decide({"score": 0.5}, {})
        assert d.action == "accept"

    def test_callable_action(self) -> None:
        default = Decision(action="noop", intensity=None, reason="noop", confidence=0.0)
        rule = Rule(
            name="dynamic",
            guard=lambda s, _st: True,
            action=lambda s, _st: Decision(
                action="dynamic",
                intensity=None,
                reason=f"score={s['score']}",
                confidence=s["score"],
            ),
        )
        c = Clutch(rules=[rule], default=default)
        d = c.decide({"score": 0.75}, {})
        assert d.action == "dynamic"
        assert d.confidence == 0.75

    def test_explain_stops_at_first_fired_rule(self) -> None:
        c = self._make_clutch()
        trace = c.explain({"score": 0.9}, {})
        assert trace[0]["fired"] is True
        # Only fired rules are included up to and including the first match
        assert len(trace) == 1

    def test_explain_shows_all_when_default_taken(self) -> None:
        c = self._make_clutch()
        trace = c.explain({"score": 0.5}, {})
        assert all(not t["fired"] for t in trace)
        assert len(trace) == 2


# ── Signal Triangulator ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestTriangulator:
    def test_basic_product(self) -> None:
        result = triangulate(0.8, 0.9, 0.7)
        assert abs(result - 0.8 * 0.9 * 0.7) < 1e-9

    def test_clamp_low(self) -> None:
        assert triangulate(-1.0, 1.0, 1.0) == 0.0

    def test_clamp_high(self) -> None:
        assert triangulate(2.0, 1.0, 1.0) == 1.2

    def test_custom_clamp(self) -> None:
        result = triangulate(1.0, 1.0, 1.0, clamp_lo=0.0, clamp_hi=0.5)
        assert result == 0.5

    def test_with_components_returns_all_fields(self) -> None:
        result = triangulate_with_components(0.8, 0.9, 0.7)
        assert "score" in result
        assert "confidence" in result
        assert "signal_strength" in result
        assert "reward" in result
        assert abs(result["reward"] - triangulate(0.8, 0.9, 0.7)) < 1e-9


# ── Trajectory Tracker ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTrajectoryTracker:
    def test_improving_label(self) -> None:
        t = TrajectoryTracker()
        state = t.update(composite=10.0, delta=0.2)
        assert state.label == "improving"

    def test_degrading_label(self) -> None:
        t = TrajectoryTracker()
        state = t.update(composite=10.0, delta=-0.2)
        assert state.label == "degrading"

    def test_flat_label(self) -> None:
        t = TrajectoryTracker()
        state = t.update(composite=10.0, delta=0.0)
        assert state.label == "flat"

    def test_failure_streak_increments_below_threshold(self) -> None:
        t = TrajectoryTracker(failure_threshold=5.0)
        t.update(composite=3.0, delta=0.0)
        state = t.update(composite=3.0, delta=0.0)
        assert state.failure_streak == 2

    def test_failure_streak_resets_above_threshold(self) -> None:
        t = TrajectoryTracker(failure_threshold=5.0)
        t.update(composite=3.0, delta=0.0)
        state = t.update(composite=10.0, delta=0.0)
        assert state.failure_streak == 0

    def test_history_is_bounded(self) -> None:
        t = TrajectoryTracker(history_cap=3)
        for i in range(10):
            t.update(composite=10.0, delta=float(i))
        assert len(t.history) <= 3


# ── Hysteresis Mode Router ────────────────────────────────────────────────────


@pytest.mark.unit
class TestHysteresisModeRouter:
    def test_stays_in_mode_during_min_duration(self) -> None:
        r = HysteresisModeRouter(modes=["a", "b"], default_mode="a", min_duration=3)
        for _ in range(2):
            d = r.decide({}, "b")
            assert d.mode == "a"
            assert not d.changed

    def test_changes_mode_after_min_duration(self) -> None:
        r = HysteresisModeRouter(modes=["a", "b"], default_mode="a", min_duration=2)
        r.decide({}, "b")
        r.decide({}, "b")
        d = r.decide({}, "b")
        assert d.mode == "b"
        assert d.changed

    def test_emergency_override_bypasses_duration(self) -> None:
        r = HysteresisModeRouter(
            modes=["a", "b"],
            default_mode="a",
            min_duration=10,
            override_conditions=[lambda s: s.get("emergency") is True],
        )
        d = r.decide({"emergency": True}, "b")
        assert d.mode == "b"
        assert d.reason == "emergency_override"

    def test_invalid_candidate_ignored(self) -> None:
        r = HysteresisModeRouter(modes=["a", "b"], default_mode="a", min_duration=0)
        d = r.decide({}, "c")  # "c" not in modes
        assert d.mode == "a"
        assert d.reason == "invalid_candidate"


# ── Component Score Composer ──────────────────────────────────────────────────


@pytest.mark.unit
class TestScoreComposer:
    def test_basic_weighted_mean(self) -> None:
        score = compose({"a": 0.8, "b": 0.6}, {"a": 0.5, "b": 0.5})
        assert abs(score.composite - 0.7) < 1e-9

    def test_components_preserved(self) -> None:
        score = compose({"x": 0.4, "y": 0.9}, {"x": 0.3, "y": 0.7})
        assert score.components == {"x": 0.4, "y": 0.9}
        assert score.weights == {"x": 0.3, "y": 0.7}

    def test_explain_returns_contributions(self) -> None:
        score = compose({"a": 1.0}, {"a": 1.0})
        explanation = score.explain()
        assert explanation[0]["component"] == "a"
        assert explanation[0]["contribution"] == 1.0

    def test_key_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="keys must match"):
            compose({"a": 0.5}, {"b": 1.0})

    def test_weight_sum_out_of_tolerance_raises(self) -> None:
        with pytest.raises(ValueError, match="sum to ~1.0"):
            compose({"a": 0.5, "b": 0.5}, {"a": 0.3, "b": 0.3})

    def test_validate_weights_false_skips_check(self) -> None:
        score = compose({"a": 0.5}, {"a": 0.3}, validate_weights=False)
        assert score.composite == 0.15


# ── Tombstone-Aware Set ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestTombstoneSet:
    def test_add_and_contains(self) -> None:
        s = TombstoneSet()
        s.add("k1", "val")
        assert "k1" in s

    def test_tombstone_removes_from_present(self) -> None:
        s = TombstoneSet()
        s.add("k1", "val")
        s.tombstone("k1", reason="test", timestamp=1000, actor="test")
        assert "k1" not in s
        assert s.state("k1") == ItemState.TOMBSTONED

    def test_tombstone_blocks_re_add(self) -> None:
        s = TombstoneSet()
        s.add("k1", "val")
        s.tombstone("k1", reason="test", timestamp=1000, actor="test")
        result = s.add("k1", "new_val")
        assert result is False
        assert "k1" not in s

    def test_restore_allows_re_add(self) -> None:
        s = TombstoneSet()
        s.add("k1", "val")
        s.tombstone("k1", reason="test", timestamp=1000, actor="test")
        s.restore("k1", "restored")
        assert "k1" in s
        assert s.get("k1") == "restored"

    def test_absent_state(self) -> None:
        s = TombstoneSet()
        assert s.state("nonexistent") == ItemState.ABSENT

    def test_get_returns_none_for_tombstoned(self) -> None:
        s = TombstoneSet()
        s.add("k1", "val")
        s.tombstone("k1", reason="test", timestamp=1000, actor="test")
        assert s.get("k1") is None

    def test_get_with_tombstones_returns_tombstone_info(self) -> None:
        s = TombstoneSet()
        s.add("k1", "val")
        s.tombstone("k1", reason="bye", timestamp=1234, actor="system")
        _, state, info = s.get_with_tombstones("k1")
        assert state == ItemState.TOMBSTONED
        assert info is not None
        assert info.reason == "bye"

    def test_len_counts_only_present(self) -> None:
        s = TombstoneSet()
        s.add("k1", 1)
        s.add("k2", 2)
        s.tombstone("k1", reason="x", timestamp=0, actor="test")
        assert len(s) == 1
