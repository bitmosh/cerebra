"""Unit tests for cerebra.cognition.stop_conditions — Phase 8 Step 2."""

from __future__ import annotations

import pytest

from cerebra.cognition.cycle_config import (
    CycleConfig,
    CycleStep,
    ClutchRule,
    StepPromptTemplate,
    StopCondition,
)
from cerebra.cognition.stop_conditions import CycleState, StopConditionEvaluator


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_config(stop_conditions: list[StopCondition]) -> CycleConfig:
    return CycleConfig(
        name="test.v0",
        version=1,
        description="",
        steps=[
            CycleStep("step_a", "", StepPromptTemplate("{{ goal }}", "free_form")),
            CycleStep("step_b", "", StepPromptTemplate("{{ goal }}", "free_form")),
        ],
        max_steps=10,
        stop_conditions=stop_conditions,
        clutch_rules=[
            ClutchRule("default", "", "always", "accept", {}),
        ],
    )


def _state(
    steps_run: int = 0,
    all_steps_completed: bool = False,
    recent_composites: list[float] | None = None,
    explicit_stop: bool = False,
    user_interrupted: bool = False,
) -> CycleState:
    return CycleState(
        steps_run=steps_run,
        all_steps_completed=all_steps_completed,
        recent_composites=recent_composites or [],
        explicit_stop=explicit_stop,
        user_interrupted=user_interrupted,
    )


# ── max_steps_reached ─────────────────────────────────────────────────────────


class TestMaxStepsReached:
    def _evaluator(self, max_steps: int = 10) -> StopConditionEvaluator:
        cfg = CycleConfig(
            name="t", version=1, description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=max_steps,
            stop_conditions=[
                StopCondition("cap", "max_steps_reached", {}),
            ],
            clutch_rules=[ClutchRule("d", "", "always", "accept", {})],
        )
        return StopConditionEvaluator(cfg)

    def test_fires_at_max(self) -> None:
        ev = self._evaluator(5)
        should_stop, name = ev.check(_state(steps_run=5))
        assert should_stop
        assert name == "cap"

    def test_fires_above_max(self) -> None:
        ev = self._evaluator(5)
        should_stop, _ = ev.check(_state(steps_run=7))
        assert should_stop

    def test_no_fire_below_max(self) -> None:
        ev = self._evaluator(5)
        should_stop, name = ev.check(_state(steps_run=4))
        assert not should_stop
        assert name is None

    def test_zero_steps_does_not_fire_with_nonzero_max(self) -> None:
        ev = self._evaluator(3)
        should_stop, _ = ev.check(_state(steps_run=0))
        assert not should_stop


# ── all_steps_completed ───────────────────────────────────────────────────────


class TestAllStepsCompleted:
    def _evaluator(self) -> StopConditionEvaluator:
        cfg = _make_config([StopCondition("done", "all_steps_completed", {})])
        return StopConditionEvaluator(cfg)

    def test_fires_when_completed(self) -> None:
        ev = self._evaluator()
        should_stop, name = ev.check(_state(all_steps_completed=True))
        assert should_stop
        assert name == "done"

    def test_no_fire_when_not_completed(self) -> None:
        ev = self._evaluator()
        should_stop, _ = ev.check(_state(all_steps_completed=False))
        assert not should_stop


# ── composite_floor_consecutive ───────────────────────────────────────────────


class TestCompositeFloorConsecutive:
    def _evaluator(self, threshold: float = 0.30, count: int = 2) -> StopConditionEvaluator:
        cfg = _make_config([
            StopCondition("floor", "composite_floor_consecutive", {
                "threshold": threshold,
                "consecutive_count": count,
            })
        ])
        return StopConditionEvaluator(cfg)

    def test_fires_when_last_n_below_threshold(self) -> None:
        ev = self._evaluator(threshold=0.30, count=2)
        should_stop, name = ev.check(_state(recent_composites=[0.7, 0.25, 0.20]))
        assert should_stop
        assert name == "floor"

    def test_no_fire_one_good_in_recent(self) -> None:
        ev = self._evaluator(threshold=0.30, count=2)
        should_stop, _ = ev.check(_state(recent_composites=[0.25, 0.50]))
        assert not should_stop

    def test_no_fire_fewer_than_count_composites(self) -> None:
        ev = self._evaluator(threshold=0.30, count=2)
        should_stop, _ = ev.check(_state(recent_composites=[0.25]))
        assert not should_stop

    def test_no_fire_empty_composites(self) -> None:
        ev = self._evaluator(threshold=0.30, count=2)
        should_stop, _ = ev.check(_state(recent_composites=[]))
        assert not should_stop

    def test_fires_exactly_at_threshold_boundary(self) -> None:
        ev = self._evaluator(threshold=0.30, count=1)
        # composite == threshold: NOT below threshold (< not <=)
        should_stop, _ = ev.check(_state(recent_composites=[0.30]))
        assert not should_stop

    def test_fires_below_threshold_by_epsilon(self) -> None:
        ev = self._evaluator(threshold=0.30, count=1)
        should_stop, _ = ev.check(_state(recent_composites=[0.2999]))
        assert should_stop


# ── explicit_clutch_stop ──────────────────────────────────────────────────────


class TestExplicitClutchStop:
    def _evaluator(self) -> StopConditionEvaluator:
        cfg = _make_config([StopCondition("xstop", "explicit_clutch_stop", {})])
        return StopConditionEvaluator(cfg)

    def test_fires_when_explicit_stop(self) -> None:
        ev = self._evaluator()
        should_stop, name = ev.check(_state(explicit_stop=True))
        assert should_stop
        assert name == "xstop"

    def test_no_fire_when_not_explicit(self) -> None:
        ev = self._evaluator()
        should_stop, _ = ev.check(_state(explicit_stop=False))
        assert not should_stop


# ── user_interrupt ────────────────────────────────────────────────────────────


class TestUserInterrupt:
    def _evaluator(self) -> StopConditionEvaluator:
        cfg = _make_config([StopCondition("intr", "user_interrupt", {})])
        return StopConditionEvaluator(cfg)

    def test_fires_when_interrupted(self) -> None:
        ev = self._evaluator()
        should_stop, name = ev.check(_state(user_interrupted=True))
        assert should_stop
        assert name == "intr"

    def test_no_fire_when_not_interrupted(self) -> None:
        ev = self._evaluator()
        should_stop, _ = ev.check(_state(user_interrupted=False))
        assert not should_stop


# ── Order and composition ─────────────────────────────────────────────────────


class TestEvaluatorOrder:
    def test_first_matching_condition_wins(self) -> None:
        cfg = _make_config([
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("done", "all_steps_completed", {}),
        ])
        ev = StopConditionEvaluator(cfg)
        # Both conditions are true; first one should win
        cfg_with_max_1 = CycleConfig(
            name="t", version=1, description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=1,
            stop_conditions=[
                StopCondition("cap", "max_steps_reached", {}),
                StopCondition("done", "all_steps_completed", {}),
            ],
            clutch_rules=[ClutchRule("d", "", "always", "accept", {})],
        )
        ev2 = StopConditionEvaluator(cfg_with_max_1)
        should_stop, name = ev2.check(_state(steps_run=1, all_steps_completed=True))
        assert should_stop
        assert name == "cap"  # first condition wins

    def test_no_condition_matches_returns_false_none(self) -> None:
        cfg = _make_config([StopCondition("cap", "max_steps_reached", {})])
        ev = StopConditionEvaluator(cfg)
        cfg_with_max_10 = CycleConfig(
            name="t", version=1, description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=10,
            stop_conditions=[StopCondition("cap", "max_steps_reached", {})],
            clutch_rules=[ClutchRule("d", "", "always", "accept", {})],
        )
        ev2 = StopConditionEvaluator(cfg_with_max_10)
        should_stop, name = ev2.check(_state(steps_run=3))
        assert not should_stop
        assert name is None
