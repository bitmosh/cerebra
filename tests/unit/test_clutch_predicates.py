# SPDX-License-Identifier: Apache-2.0
"""Phase 9 Step 1 unit tests — new ClutchEngine predicates and cascade_depth.

Tests for:
  - 7 new state-aware predicates + catalyst_was_invoked placeholder
  - ClutchDecision.cascade_depth population
  - ClutchDecision.escalate_to_catalyst flag behavior
  - ClutchCycleState tracking in CycleRuntime (via integration)
  - CycleConfig.composite_floor (non-breaking default)
  - simple.planning.v0 regression: escalate_to_catalyst never fires, behavior unchanged
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from cerebra.cognition.clutch import (
    BUILTIN_PREDICATES,
    ClutchContext,
    ClutchCycleState,
    ClutchDecision,
    ClutchEngine,
)
from cerebra.cognition.cycle_config import (
    ClutchRule,
    CycleConfig,
    CycleStep,
    StepPromptTemplate,
    StopCondition,
    _parse_config,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ctx(
    step_index: int = 0,
    step_count: int = 5,
    composite_score: float = 0.7,
    last_clutch_action: str | None = None,
    total_steps_run: int = 0,
    evaluation: Any = None,
    outcome: Any = None,
    cycle_state: ClutchCycleState | None = None,
    cycle_config: Any = None,
) -> ClutchContext:
    return ClutchContext(
        step_index=step_index,
        step_count=step_count,
        composite_score=composite_score,
        last_clutch_action=last_clutch_action,
        total_steps_run=total_steps_run,
        evaluation=evaluation,
        outcome=outcome,
        cycle_state=cycle_state or ClutchCycleState(),
        cycle_config=cycle_config,
    )


def _mock_evaluation(per_signal_scores: dict[str, float]) -> Any:
    ev = MagicMock()
    ev.per_signal_scores = per_signal_scores
    return ev


def _mock_outcome(error_classification: str) -> Any:
    oc = MagicMock()
    oc.error_classification = error_classification
    return oc


def _make_config_with_rules(rules: list[dict], composite_floor: float = 0.3) -> object:
    d = {
        "name": "test.v0",
        "version": 1,
        "description": "",
        "max_steps": 10,
        "composite_floor": composite_floor,
        "steps": [
            {
                "name": f"step_{i}",
                "description": "",
                "prompt_template": {
                    "template": "{{ goal }}",
                    "expected_output_format": "free_form",
                },
            }
            for i in range(3)
        ],
        "stop_conditions": [{"name": "cap", "type": "max_steps_reached", "parameters": {}}],
        "clutch_rules": rules,
    }
    return _parse_config(d)


# ── prediction_severe_miss ────────────────────────────────────────────────────


class TestPredictionSevereMiss:
    def test_true_when_severe(self) -> None:
        ctx = _ctx(outcome=_mock_outcome("severe"))
        assert BUILTIN_PREDICATES["prediction_severe_miss"](ctx, {})

    def test_false_when_notable(self) -> None:
        ctx = _ctx(outcome=_mock_outcome("notable"))
        assert not BUILTIN_PREDICATES["prediction_severe_miss"](ctx, {})

    def test_false_when_noise(self) -> None:
        ctx = _ctx(outcome=_mock_outcome("noise"))
        assert not BUILTIN_PREDICATES["prediction_severe_miss"](ctx, {})

    def test_false_when_outcome_none(self) -> None:
        ctx = _ctx(outcome=None)
        assert not BUILTIN_PREDICATES["prediction_severe_miss"](ctx, {})


# ── prediction_notable_miss ───────────────────────────────────────────────────


class TestPredictionNotableMiss:
    def test_true_when_notable(self) -> None:
        ctx = _ctx(outcome=_mock_outcome("notable"))
        assert BUILTIN_PREDICATES["prediction_notable_miss"](ctx, {})

    def test_true_when_severe(self) -> None:
        ctx = _ctx(outcome=_mock_outcome("severe"))
        assert BUILTIN_PREDICATES["prediction_notable_miss"](ctx, {})

    def test_false_when_noise(self) -> None:
        ctx = _ctx(outcome=_mock_outcome("noise"))
        assert not BUILTIN_PREDICATES["prediction_notable_miss"](ctx, {})

    def test_false_when_outcome_none(self) -> None:
        ctx = _ctx(outcome=None)
        assert not BUILTIN_PREDICATES["prediction_notable_miss"](ctx, {})


# ── signal_below_threshold ────────────────────────────────────────────────────


class TestSignalBelowThreshold:
    def test_true_when_below(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"COHERENCE": 0.3}))
        assert BUILTIN_PREDICATES["signal_below_threshold"](
            ctx, {"signal": "COHERENCE", "threshold": 0.5}
        )

    def test_false_when_at_threshold(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"COHERENCE": 0.5}))
        assert not BUILTIN_PREDICATES["signal_below_threshold"](
            ctx, {"signal": "COHERENCE", "threshold": 0.5}
        )

    def test_false_when_above(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"COHERENCE": 0.8}))
        assert not BUILTIN_PREDICATES["signal_below_threshold"](
            ctx, {"signal": "COHERENCE", "threshold": 0.5}
        )

    def test_false_when_signal_absent(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"RELEVANCE": 0.3}))
        assert not BUILTIN_PREDICATES["signal_below_threshold"](
            ctx, {"signal": "COHERENCE", "threshold": 0.5}
        )

    def test_false_when_evaluation_none(self) -> None:
        ctx = _ctx(evaluation=None)
        assert not BUILTIN_PREDICATES["signal_below_threshold"](
            ctx, {"signal": "COHERENCE", "threshold": 0.5}
        )


# ── signal_above_threshold ────────────────────────────────────────────────────


class TestSignalAboveThreshold:
    def test_true_when_above(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"GROUNDEDNESS": 0.9}))
        assert BUILTIN_PREDICATES["signal_above_threshold"](
            ctx, {"signal": "GROUNDEDNESS", "threshold": 0.7}
        )

    def test_true_when_at_threshold(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"GROUNDEDNESS": 0.7}))
        assert BUILTIN_PREDICATES["signal_above_threshold"](
            ctx, {"signal": "GROUNDEDNESS", "threshold": 0.7}
        )

    def test_false_when_below(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"GROUNDEDNESS": 0.4}))
        assert not BUILTIN_PREDICATES["signal_above_threshold"](
            ctx, {"signal": "GROUNDEDNESS", "threshold": 0.7}
        )

    def test_false_when_signal_absent(self) -> None:
        ctx = _ctx(evaluation=_mock_evaluation({"COHERENCE": 0.9}))
        assert not BUILTIN_PREDICATES["signal_above_threshold"](
            ctx, {"signal": "GROUNDEDNESS", "threshold": 0.7}
        )

    def test_false_when_evaluation_none(self) -> None:
        ctx = _ctx(evaluation=None)
        assert not BUILTIN_PREDICATES["signal_above_threshold"](
            ctx, {"signal": "GROUNDEDNESS", "threshold": 0.7}
        )


# ── consecutive_steps_below_floor ─────────────────────────────────────────────


class TestConsecutiveStepsBelowFloor:
    def test_true_when_count_met(self) -> None:
        state = ClutchCycleState(consecutive_steps_below_floor=3)
        ctx = _ctx(cycle_state=state)
        assert BUILTIN_PREDICATES["consecutive_steps_below_floor"](ctx, {"count": 3})

    def test_true_when_count_exceeded(self) -> None:
        state = ClutchCycleState(consecutive_steps_below_floor=5)
        ctx = _ctx(cycle_state=state)
        assert BUILTIN_PREDICATES["consecutive_steps_below_floor"](ctx, {"count": 2})

    def test_false_when_count_not_met(self) -> None:
        state = ClutchCycleState(consecutive_steps_below_floor=1)
        ctx = _ctx(cycle_state=state)
        assert not BUILTIN_PREDICATES["consecutive_steps_below_floor"](ctx, {"count": 2})

    def test_false_when_zero(self) -> None:
        state = ClutchCycleState(consecutive_steps_below_floor=0)
        ctx = _ctx(cycle_state=state)
        assert not BUILTIN_PREDICATES["consecutive_steps_below_floor"](ctx, {"count": 1})

    def test_default_state_is_zero(self) -> None:
        ctx = _ctx()  # default ClutchCycleState
        assert not BUILTIN_PREDICATES["consecutive_steps_below_floor"](ctx, {"count": 1})


# ── prior_step_action_was ─────────────────────────────────────────────────────


class TestPriorStepActionWas:
    def _decision(self, action: str) -> ClutchDecision:
        return ClutchDecision(action=action, rule_matched="r")

    def test_true_when_prior_action_matches(self) -> None:
        state = ClutchCycleState(prior_clutch_decisions=[self._decision("refine")])
        ctx = _ctx(cycle_state=state)
        assert BUILTIN_PREDICATES["prior_step_action_was"](ctx, {"action": "refine"})

    def test_true_reads_last_decision(self) -> None:
        state = ClutchCycleState(
            prior_clutch_decisions=[
                self._decision("accept"),
                self._decision("refine"),
            ]
        )
        ctx = _ctx(cycle_state=state)
        assert BUILTIN_PREDICATES["prior_step_action_was"](ctx, {"action": "refine"})

    def test_false_when_action_differs(self) -> None:
        state = ClutchCycleState(prior_clutch_decisions=[self._decision("accept")])
        ctx = _ctx(cycle_state=state)
        assert not BUILTIN_PREDICATES["prior_step_action_was"](ctx, {"action": "refine"})

    def test_false_when_no_prior_decisions(self) -> None:
        state = ClutchCycleState(prior_clutch_decisions=[])
        ctx = _ctx(cycle_state=state)
        assert not BUILTIN_PREDICATES["prior_step_action_was"](ctx, {"action": "refine"})

    def test_false_when_default_empty_state(self) -> None:
        ctx = _ctx()
        assert not BUILTIN_PREDICATES["prior_step_action_was"](ctx, {"action": "accept"})


# ── step_at ───────────────────────────────────────────────────────────────────


class TestStepAt:
    def _config_with_steps(self, names: list[str]) -> Any:
        cfg = MagicMock()
        cfg.steps = [MagicMock(name=n) for n in names]
        for i, name in enumerate(names):
            cfg.steps[i].name = name
        return cfg

    def test_true_when_step_name_matches(self) -> None:
        cfg = self._config_with_steps(["plan", "critique", "finalize"])
        ctx = _ctx(step_index=1, cycle_config=cfg)
        assert BUILTIN_PREDICATES["step_at"](ctx, {"step_name": "critique"})

    def test_false_when_step_name_differs(self) -> None:
        cfg = self._config_with_steps(["plan", "critique", "finalize"])
        ctx = _ctx(step_index=1, cycle_config=cfg)
        assert not BUILTIN_PREDICATES["step_at"](ctx, {"step_name": "plan"})

    def test_false_when_cycle_config_none(self) -> None:
        ctx = _ctx(cycle_config=None)
        assert not BUILTIN_PREDICATES["step_at"](ctx, {"step_name": "plan"})

    def test_false_when_step_index_out_of_bounds(self) -> None:
        cfg = self._config_with_steps(["plan"])
        ctx = _ctx(step_index=5, cycle_config=cfg)
        assert not BUILTIN_PREDICATES["step_at"](ctx, {"step_name": "plan"})


# ── catalyst_was_invoked ──────────────────────────────────────────────────────


class TestCatalystWasInvoked:
    def test_always_false_in_step1(self) -> None:
        assert not BUILTIN_PREDICATES["catalyst_was_invoked"](_ctx(), {})

    def test_always_false_with_any_state(self) -> None:
        state = ClutchCycleState(consecutive_steps_below_floor=10)
        ctx = _ctx(cycle_state=state, composite_score=0.0)
        assert not BUILTIN_PREDICATES["catalyst_was_invoked"](ctx, {})


# ── ClutchDecision.cascade_depth ─────────────────────────────────────────────


class TestCascadeDepth:
    def _engine(self, rules: list[dict]) -> ClutchEngine:
        cfg = _make_config_with_rules(rules)
        return ClutchEngine(cfg)  # type: ignore[arg-type]

    def test_cascade_depth_zero_for_first_rule(self) -> None:
        engine = self._engine(
            [
                {
                    "name": "r0",
                    "description": "",
                    "predicate_name": "always",
                    "action": "accept",
                    "parameters": {},
                },
                {
                    "name": "r1",
                    "description": "",
                    "predicate_name": "always",
                    "action": "stop",
                    "parameters": {},
                },
            ]
        )
        decision = engine.decide(_ctx())
        assert decision.cascade_depth == 0

    def test_cascade_depth_one_for_second_rule(self) -> None:
        engine = self._engine(
            [
                {
                    "name": "r0",
                    "description": "",
                    "predicate_name": "first_step",
                    "action": "stop",
                    "parameters": {},
                },
                {
                    "name": "r1",
                    "description": "",
                    "predicate_name": "always",
                    "action": "accept",
                    "parameters": {},
                },
            ]
        )
        # step_index=2 so first_step is False → second rule fires
        decision = engine.decide(_ctx(step_index=2))
        assert decision.cascade_depth == 1

    def test_cascade_depth_equals_rule_count_when_no_match(self) -> None:
        cfg = CycleConfig(
            name="x",
            version=1,
            description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=5,
            stop_conditions=[StopCondition("cap", "max_steps_reached", {})],
            clutch_rules=[
                ClutchRule("r0", "", "step_index_at", "accept", {"index": 99}),
                ClutchRule("r1", "", "step_index_at", "accept", {"index": 98}),
            ],
        )
        engine = ClutchEngine(cfg)
        decision = engine.decide(_ctx(step_index=0))
        assert decision.cascade_depth == 2  # len(rules)

    def test_cascade_depth_default_zero(self) -> None:
        d = ClutchDecision(action="accept", rule_matched="r")
        assert d.cascade_depth == 0


# ── escalate_to_catalyst flag ────────────────────────────────────────────────


class TestEscalateToCatalyst:
    def _engine(self, rules: list[dict]) -> ClutchEngine:
        cfg = _make_config_with_rules(rules)
        return ClutchEngine(cfg)  # type: ignore[arg-type]

    def test_escalate_false_when_rule_matches(self) -> None:
        engine = self._engine(
            [
                {
                    "name": "r",
                    "description": "",
                    "predicate_name": "always",
                    "action": "accept",
                    "parameters": {},
                },
            ]
        )
        decision = engine.decide(_ctx())
        assert decision.escalate_to_catalyst is False

    def test_escalate_true_when_no_rule_matches(self) -> None:
        cfg = CycleConfig(
            name="x",
            version=1,
            description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=5,
            stop_conditions=[StopCondition("cap", "max_steps_reached", {})],
            clutch_rules=[ClutchRule("no_match", "", "step_index_at", "accept", {"index": 99})],
        )
        engine = ClutchEngine(cfg)
        decision = engine.decide(_ctx(step_index=0))
        assert decision.escalate_to_catalyst is True

    def test_escalate_false_default(self) -> None:
        d = ClutchDecision(action="accept", rule_matched="r")
        assert d.escalate_to_catalyst is False

    def test_no_match_action_is_accept_safe_default(self) -> None:
        cfg = CycleConfig(
            name="x",
            version=1,
            description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=5,
            stop_conditions=[StopCondition("cap", "max_steps_reached", {})],
            clutch_rules=[ClutchRule("no_match", "", "step_index_at", "accept", {"index": 99})],
        )
        engine = ClutchEngine(cfg)
        decision = engine.decide(_ctx(step_index=0))
        assert decision.action == "accept"
        assert decision.rule_matched == "default_no_match"


# ── CycleConfig.composite_floor ───────────────────────────────────────────────


class TestCompositeFLoor:
    def test_default_is_0_3(self) -> None:
        cfg = _make_config_with_rules(
            [
                {
                    "name": "r",
                    "description": "",
                    "predicate_name": "always",
                    "action": "accept",
                    "parameters": {},
                },
            ]
        )
        assert cfg.composite_floor == 0.3  # type: ignore[union-attr]

    def test_custom_floor_from_yaml(self) -> None:
        cfg = _make_config_with_rules(
            [
                {
                    "name": "r",
                    "description": "",
                    "predicate_name": "always",
                    "action": "accept",
                    "parameters": {},
                },
            ],
            composite_floor=0.5,
        )
        assert cfg.composite_floor == 0.5  # type: ignore[union-attr]

    def test_old_configs_without_floor_still_parse(self) -> None:
        d = {
            "name": "legacy.v0",
            "version": 1,
            "description": "",
            "max_steps": 5,
            "steps": [
                {
                    "name": "s",
                    "description": "",
                    "prompt_template": {
                        "template": "{{ goal }}",
                        "expected_output_format": "free_form",
                    },
                }
            ],
            "stop_conditions": [{"name": "cap", "type": "max_steps_reached", "parameters": {}}],
            "clutch_rules": [
                {
                    "name": "r",
                    "description": "",
                    "predicate_name": "always",
                    "action": "accept",
                    "parameters": {},
                }
            ],
            # NOTE: no composite_floor key
        }
        cfg = _parse_config(d)
        assert cfg.composite_floor == 0.3  # default applied


# ── ClutchCycleState ──────────────────────────────────────────────────────────


class TestClutchCycleState:
    def test_default_consecutive_is_zero(self) -> None:
        state = ClutchCycleState()
        assert state.consecutive_steps_below_floor == 0

    def test_default_prior_decisions_empty(self) -> None:
        state = ClutchCycleState()
        assert state.prior_clutch_decisions == []

    def test_mutable_increment(self) -> None:
        state = ClutchCycleState()
        state.consecutive_steps_below_floor += 1
        assert state.consecutive_steps_below_floor == 1

    def test_reset_to_zero(self) -> None:
        state = ClutchCycleState(consecutive_steps_below_floor=3)
        state.consecutive_steps_below_floor = 0
        assert state.consecutive_steps_below_floor == 0

    def test_append_prior_decisions(self) -> None:
        state = ClutchCycleState()
        state.prior_clutch_decisions.append(ClutchDecision("accept", "r"))
        assert len(state.prior_clutch_decisions) == 1


# ── simple.planning.v0 regression ────────────────────────────────────────────


class TestSimplePlanningV0Regression:
    def _load_engine(self) -> ClutchEngine:
        from cerebra.cognition.cycle_config import CycleConfigLoader

        cfg = CycleConfigLoader().load("simple.planning.v0")
        return ClutchEngine(cfg)

    def test_non_terminal_good_score_accepts(self) -> None:
        engine = self._load_engine()
        ctx = _ctx(step_index=2, step_count=5, composite_score=0.7)
        d = engine.decide(ctx)
        assert d.action == "accept"
        assert d.escalate_to_catalyst is False

    def test_low_score_refines(self) -> None:
        engine = self._load_engine()
        ctx = _ctx(step_index=2, step_count=5, composite_score=0.4)
        d = engine.decide(ctx)
        assert d.action == "refine"
        assert d.escalate_to_catalyst is False

    def test_catastrophic_first_step_stops(self) -> None:
        engine = self._load_engine()
        ctx = _ctx(step_index=0, step_count=5, composite_score=0.2)
        d = engine.decide(ctx)
        assert d.action == "stop"
        assert d.escalate_to_catalyst is False

    def test_escalate_never_fires_on_simple_planning(self) -> None:
        """simple.planning.v0 has an 'always' default-accept rule; escalate must never fire."""
        engine = self._load_engine()
        for step_index in range(5):
            for score in [0.1, 0.3, 0.5, 0.7, 0.9]:
                ctx = _ctx(step_index=step_index, step_count=5, composite_score=score)
                d = engine.decide(ctx)
                assert d.escalate_to_catalyst is False, (
                    f"escalate_to_catalyst should never fire on simple.planning.v0 "
                    f"(step_index={step_index}, score={score}, rule={d.rule_matched})"
                )

    def test_cascade_depth_populated(self) -> None:
        engine = self._load_engine()
        ctx = _ctx(step_index=2, step_count=5, composite_score=0.7)
        d = engine.decide(ctx)
        assert isinstance(d.cascade_depth, int)
        assert d.cascade_depth >= 0

    def test_new_predicate_names_valid_in_config(self) -> None:
        """Verify expanded BUILTIN_PREDICATE_NAMES accepts new names."""
        from cerebra.cognition._constants import BUILTIN_PREDICATE_NAMES

        new_predicates = [
            "prediction_severe_miss",
            "prediction_notable_miss",
            "signal_below_threshold",
            "signal_above_threshold",
            "consecutive_steps_below_floor",
            "prior_step_action_was",
            "step_at",
            "catalyst_was_invoked",
        ]
        for name in new_predicates:
            assert name in BUILTIN_PREDICATE_NAMES, f"{name} missing from BUILTIN_PREDICATE_NAMES"
