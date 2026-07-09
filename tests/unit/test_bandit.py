# SPDX-License-Identifier: Apache-2.0
"""Unit tests for cerebra._primitives.bandit — Phase 9 Step 2.

Covers the 19 test cases from LATTICA_PRIMITIVES.md §11 "Test requirements".
"""

from __future__ import annotations

import random

import pytest

from cerebra._primitives.bandit import ArmStats, Bandit

# ── Helpers ───────────────────────────────────────────────────────────────────

ARMS = ["explore", "refine", "stop"]


def _seeded(seed: int = 42) -> Bandit:
    return Bandit(rng=random.Random(seed))


def _with_updates(arms: list[str], rewards: list[float], seed: int = 42) -> Bandit:
    """Create a bandit that has seen each arm once with the given reward."""
    b = _seeded(seed)
    for arm, reward in zip(arms, rewards, strict=True):
        b.update(arm, reward)
    return b


# ── ArmStats math ─────────────────────────────────────────────────────────────


class TestArmStats:
    def test_mean_reward_zero_when_count_zero(self) -> None:
        stats = ArmStats()
        assert stats.mean_reward == 0.0

    def test_mean_reward_computes_correctly_when_count_positive(self) -> None:
        stats = ArmStats(count=4, total_reward=2.0)
        assert stats.mean_reward == pytest.approx(0.5)


# ── ensure_arms ───────────────────────────────────────────────────────────────


class TestEnsureArms:
    def test_ensure_arms_idempotent(self) -> None:
        b = Bandit()
        b.ensure_arms(ARMS)
        b.ensure_arms(ARMS)
        assert set(b.arms.keys()) == set(ARMS)
        for arm in ARMS:
            assert b.arms[arm].count == 0

    def test_ensure_arms_preserves_existing_stats(self) -> None:
        b = Bandit()
        b.update("explore", 0.8)
        b.ensure_arms(["explore", "refine"])
        assert b.arms["explore"].count == 1
        assert b.arms["explore"].total_reward == pytest.approx(0.8)
        assert b.arms["refine"].count == 0


# ── select ────────────────────────────────────────────────────────────────────


class TestSelect:
    def test_select_on_empty_arm_list_raises(self) -> None:
        b = Bandit()
        with pytest.raises(ValueError):
            b.select([], total_steps=0)

    def test_select_picks_first_unseen_arm_with_forced_exploration(self) -> None:
        b = Bandit()
        result = b.select(ARMS, total_steps=0)
        assert result.arm == "explore"
        assert result.selection_reason == "forced_exploration"
        assert result.ucb_score == float("inf")
        assert result.exploration_bonus == float("inf")
        assert result.candidates_seen == len(ARMS)

    def test_select_on_all_explored_arms_applies_ucb(self) -> None:
        b = _with_updates(ARMS, [0.9, 0.5, 0.1])
        result = b.select(ARMS, total_steps=3)
        assert result.selection_reason == "ucb_score"
        assert result.ucb_score != float("inf")
        # "explore" has highest mean (0.9), should win the UCB race
        assert result.arm == "explore"

    def test_select_updates_last_selected_step_on_chosen_arm(self) -> None:
        b = Bandit()
        result = b.select(ARMS, total_steps=7)
        assert b.arms[result.arm].last_selected_step == 7

    def test_select_ties_broken_by_declaration_order(self) -> None:
        # Two arms with identical count and total_reward → identical UCB score
        # First in list wins (strict > comparison means first stays)
        b = Bandit()
        b.update("alpha", 0.5)
        b.update("beta", 0.5)
        result = b.select(["alpha", "beta"], total_steps=2)
        assert result.arm == "alpha"
        assert result.selection_reason == "ucb_score"


# ── update ────────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_increments_count_by_one(self) -> None:
        b = Bandit()
        b.update("explore", 0.7)
        assert b.arms["explore"].count == 1

    def test_update_adds_reward_to_total(self) -> None:
        b = Bandit()
        b.update("explore", 0.7)
        b.update("explore", 0.3)
        assert b.arms["explore"].total_reward == pytest.approx(1.0)

    def test_update_creates_arm_if_missing(self) -> None:
        b = Bandit()
        assert "explore" not in b.arms
        b.update("explore", 0.5)
        assert "explore" in b.arms
        assert b.arms["explore"].count == 1

    def test_update_accepts_negative_reward(self) -> None:
        b = Bandit()
        b.update("explore", -0.3)
        assert b.arms["explore"].total_reward == pytest.approx(-0.3)


# ── get_stats ─────────────────────────────────────────────────────────────────


class TestGetStats:
    def test_get_stats_returns_default_for_unknown_arm(self) -> None:
        b = Bandit()
        stats = b.get_stats("never_seen")
        assert stats.count == 0
        assert stats.total_reward == 0.0
        assert stats.mean_reward == 0.0

    def test_get_stats_returns_actual_stats_for_known_arm(self) -> None:
        b = Bandit()
        b.update("explore", 0.75)
        b.update("explore", 0.25)
        stats = b.get_stats("explore")
        assert stats.count == 2
        assert stats.total_reward == pytest.approx(1.0)
        assert stats.mean_reward == pytest.approx(0.5)


# ── explain ───────────────────────────────────────────────────────────────────


class TestExplain:
    def test_explain_produces_trace_for_all_candidates(self) -> None:
        b = _with_updates(ARMS, [0.8, 0.5, 0.2])
        trace = b.explain(ARMS, total_steps=3)
        assert len(trace) == len(ARMS)
        arm_names = [entry["arm"] for entry in trace]
        assert arm_names == ARMS

    def test_explain_reports_infinite_scores_for_unselected_arms(self) -> None:
        b = Bandit()
        trace = b.explain(ARMS, total_steps=0)
        for entry in trace:
            assert entry["count"] == 0
            assert entry["ucb_score"] == float("inf")
            assert entry["exploration_bonus"] == float("inf")

    def test_explain_trace_fields_present(self) -> None:
        b = _with_updates(["explore"], [0.6])
        trace = b.explain(["explore"], total_steps=1)
        entry = trace[0]
        assert set(entry.keys()) == {
            "arm",
            "count",
            "mean_reward",
            "exploration_bonus",
            "ucb_score",
        }


# ── Serialization ─────────────────────────────────────────────────────────────


class TestSerialization:
    def test_to_state_from_state_round_trip(self) -> None:
        b = _with_updates(ARMS, [0.9, 0.5, 0.1])
        _ = b.select(ARMS, total_steps=3)  # set last_selected_step on winner

        state = b.to_state()
        b2 = Bandit.from_state(state)

        assert b2.exploration_weight == b.exploration_weight
        for arm in ARMS:
            assert b2.arms[arm].count == b.arms[arm].count
            assert b2.arms[arm].total_reward == pytest.approx(b.arms[arm].total_reward)
            assert b2.arms[arm].last_selected_step == b.arms[arm].last_selected_step

    def test_from_state_with_missing_fields_uses_defaults(self) -> None:
        state: dict = {"arms": {"explore": {"count": 2, "total_reward": 1.0}}}
        b = Bandit.from_state(state)
        assert b.exploration_weight == 1.4
        assert b.arms["explore"].count == 2
        assert b.arms["explore"].last_selected_step is None


# ── Determinism ───────────────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_seed_same_operations_produce_identical_state(self) -> None:
        def run(seed: int) -> Bandit:
            b = Bandit(rng=random.Random(seed))
            b.update("explore", 0.8)
            b.update("refine", 0.5)
            b.update("stop", 0.1)
            b.select(ARMS, total_steps=3)
            b.update("explore", 0.9)
            b.select(ARMS, total_steps=4)
            return b

        b1 = run(42)
        b2 = run(42)

        for arm in ARMS:
            assert b1.arms[arm].count == b2.arms[arm].count
            assert b1.arms[arm].total_reward == pytest.approx(b2.arms[arm].total_reward)
            assert b1.arms[arm].last_selected_step == b2.arms[arm].last_selected_step
