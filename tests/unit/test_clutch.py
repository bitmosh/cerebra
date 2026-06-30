"""Unit tests for cerebra.cognition.clutch — Phase 9 Step 1 (renamed from clutch_stub)."""

from __future__ import annotations

import pytest

from cerebra.cognition.clutch import (
    BUILTIN_PREDICATES,
    ClutchContext,
    ClutchDecision,
    ClutchEngine,
)
from cerebra.cognition.cycle_config import _parse_config

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _ctx(
    step_index: int = 0,
    step_count: int = 5,
    composite_score: float = 0.7,
    last_clutch_action: str | None = None,
    total_steps_run: int = 0,
) -> ClutchContext:
    return ClutchContext(
        step_index=step_index,
        step_count=step_count,
        composite_score=composite_score,
        last_clutch_action=last_clutch_action,
        total_steps_run=total_steps_run,
    )


def _make_config_with_rules(rules: list[dict]) -> object:
    d = {
        "name": "test.v0",
        "version": 1,
        "description": "",
        "max_steps": 10,
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
        "stop_conditions": [
            {"name": "cap", "type": "max_steps_reached", "parameters": {}}
        ],
        "clutch_rules": rules,
    }
    return _parse_config(d)


# ── ClutchContext ──────────────────────────────────────────────────────────────


class TestClutchContext:
    def test_frozen(self) -> None:
        ctx = _ctx()
        with pytest.raises((AttributeError, TypeError)):
            ctx.composite_score = 0.9  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        ctx = _ctx(step_index=2, step_count=5, composite_score=0.5)
        assert ctx.step_index == 2
        assert ctx.step_count == 5
        assert ctx.composite_score == 0.5


# ── BUILTIN_PREDICATES ────────────────────────────────────────────────────────


class TestBuiltinPredicates:
    # at_terminal_step

    def test_at_terminal_step_true_at_last(self) -> None:
        ctx = _ctx(step_index=4, step_count=5, composite_score=0.6)
        assert BUILTIN_PREDICATES["at_terminal_step"](ctx, {"min_composite": 0.5})

    def test_at_terminal_step_false_not_last(self) -> None:
        ctx = _ctx(step_index=3, step_count=5, composite_score=0.9)
        assert not BUILTIN_PREDICATES["at_terminal_step"](ctx, {"min_composite": 0.5})

    def test_at_terminal_step_false_below_min_composite(self) -> None:
        ctx = _ctx(step_index=4, step_count=5, composite_score=0.3)
        assert not BUILTIN_PREDICATES["at_terminal_step"](ctx, {"min_composite": 0.5})

    def test_at_terminal_step_no_min_composite_defaults_zero(self) -> None:
        ctx = _ctx(step_index=4, step_count=5, composite_score=0.0)
        assert BUILTIN_PREDICATES["at_terminal_step"](ctx, {})

    # composite_below_threshold

    def test_below_threshold_true(self) -> None:
        ctx = _ctx(composite_score=0.25)
        assert BUILTIN_PREDICATES["composite_below_threshold"](ctx, {"threshold": 0.30})

    def test_below_threshold_false_equal(self) -> None:
        ctx = _ctx(composite_score=0.30)
        assert not BUILTIN_PREDICATES["composite_below_threshold"](ctx, {"threshold": 0.30})

    def test_below_threshold_false_above(self) -> None:
        ctx = _ctx(composite_score=0.55)
        assert not BUILTIN_PREDICATES["composite_below_threshold"](ctx, {"threshold": 0.50})

    def test_below_threshold_with_first_step_constraint_true(self) -> None:
        ctx = _ctx(step_index=0, composite_score=0.2)
        assert BUILTIN_PREDICATES["composite_below_threshold"](
            ctx, {"threshold": 0.30, "with_constraint": "first_step"}
        )

    def test_below_threshold_with_first_step_constraint_false_not_first(self) -> None:
        ctx = _ctx(step_index=2, composite_score=0.2)
        assert not BUILTIN_PREDICATES["composite_below_threshold"](
            ctx, {"threshold": 0.30, "with_constraint": "first_step"}
        )

    def test_below_threshold_with_first_step_false_above_threshold(self) -> None:
        ctx = _ctx(step_index=0, composite_score=0.5)
        assert not BUILTIN_PREDICATES["composite_below_threshold"](
            ctx, {"threshold": 0.30, "with_constraint": "first_step"}
        )

    # composite_above_threshold

    def test_above_threshold_true(self) -> None:
        ctx = _ctx(composite_score=0.8)
        assert BUILTIN_PREDICATES["composite_above_threshold"](ctx, {"threshold": 0.7})

    def test_above_threshold_true_equal(self) -> None:
        ctx = _ctx(composite_score=0.7)
        assert BUILTIN_PREDICATES["composite_above_threshold"](ctx, {"threshold": 0.7})

    def test_above_threshold_false(self) -> None:
        ctx = _ctx(composite_score=0.4)
        assert not BUILTIN_PREDICATES["composite_above_threshold"](ctx, {"threshold": 0.7})

    # first_step

    def test_first_step_true(self) -> None:
        ctx = _ctx(step_index=0)
        assert BUILTIN_PREDICATES["first_step"](ctx, {})

    def test_first_step_false(self) -> None:
        ctx = _ctx(step_index=1)
        assert not BUILTIN_PREDICATES["first_step"](ctx, {})

    # step_index_at

    def test_step_index_at_match(self) -> None:
        ctx = _ctx(step_index=3)
        assert BUILTIN_PREDICATES["step_index_at"](ctx, {"index": 3})

    def test_step_index_at_no_match(self) -> None:
        ctx = _ctx(step_index=2)
        assert not BUILTIN_PREDICATES["step_index_at"](ctx, {"index": 3})

    # always

    def test_always_true(self) -> None:
        assert BUILTIN_PREDICATES["always"](_ctx(), {})
        assert BUILTIN_PREDICATES["always"](_ctx(composite_score=0.0), {})


# ── ClutchEngine ──────────────────────────────────────────────────────────


class TestClutchEngine:
    def _engine(self, rules: list[dict]) -> ClutchEngine:
        cfg = _make_config_with_rules(rules)
        return ClutchEngine(cfg)  # type: ignore[arg-type]

    def test_first_matching_rule_wins(self) -> None:
        engine = self._engine([
            {"name": "r1", "description": "", "predicate_name": "always", "action": "stop", "parameters": {}},
            {"name": "r2", "description": "", "predicate_name": "always", "action": "accept", "parameters": {}},
        ])
        decision = engine.decide(_ctx())
        assert decision.action == "stop"
        assert decision.rule_matched == "r1"

    def test_default_accept_when_no_rule_matches(self) -> None:
        # Only rule is first_step but we're at step 2
        engine = self._engine([
            {"name": "first_only", "description": "", "predicate_name": "first_step", "action": "stop", "parameters": {}},
            {"name": "default", "description": "", "predicate_name": "always", "action": "accept", "parameters": {}},
        ])
        ctx = _ctx(step_index=2)
        decision = engine.decide(ctx)
        assert decision.action == "accept"
        assert decision.rule_matched == "default"

    def test_no_match_returns_default_no_match(self) -> None:
        # Make an engine with no always rule but only step_index_at=99
        engine = self._engine([
            {"name": "unreachable", "description": "", "predicate_name": "step_index_at", "action": "stop", "parameters": {"index": 99}},
            {"name": "accept", "description": "", "predicate_name": "always", "action": "accept", "parameters": {}},
        ])
        # The "always" rule fires so default_no_match won't be hit; test the fallback
        # by building a config where NO rule would match:
        from cerebra.cognition.cycle_config import (
            ClutchRule,
            CycleConfig,
            CycleStep,
            StepPromptTemplate,
            StopCondition,
        )
        cfg = CycleConfig(
            name="x", version=1, description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=5,
            stop_conditions=[StopCondition("cap", "max_steps_reached", {})],
            clutch_rules=[ClutchRule("no_match", "", "step_index_at", "accept", {"index": 99})],
        )
        real_engine = ClutchEngine(cfg)
        decision = real_engine.decide(_ctx(step_index=0))
        assert decision.action == "accept"
        assert decision.rule_matched == "default_no_match"

    def test_decision_frozen(self) -> None:
        engine = self._engine([
            {"name": "r", "description": "", "predicate_name": "always", "action": "accept", "parameters": {}},
        ])
        decision = engine.decide(_ctx())
        assert isinstance(decision, ClutchDecision)
        with pytest.raises((AttributeError, TypeError)):
            decision.action = "stop"  # type: ignore[misc]

    def test_escalate_false_when_rule_matches(self) -> None:
        engine = self._engine([
            {"name": "r", "description": "", "predicate_name": "always", "action": "accept", "parameters": {}},
        ])
        decision = engine.decide(_ctx())
        assert decision.escalate_to_catalyst is False

    def test_simple_planning_config_happy_path(self) -> None:
        loader = __import__("cerebra.cognition.cycle_config", fromlist=["CycleConfigLoader"]).CycleConfigLoader
        cfg = loader().load("simple.planning.v0")
        engine = ClutchEngine(cfg)

        # Non-terminal step with good score → default_accept
        ctx = _ctx(step_index=2, step_count=5, composite_score=0.7)
        d = engine.decide(ctx)
        assert d.action == "accept"

    def test_simple_planning_refine_low_score(self) -> None:
        loader = __import__("cerebra.cognition.cycle_config", fromlist=["CycleConfigLoader"]).CycleConfigLoader
        cfg = loader().load("simple.planning.v0")
        engine = ClutchEngine(cfg)

        ctx = _ctx(step_index=2, step_count=5, composite_score=0.4)
        d = engine.decide(ctx)
        assert d.action == "refine"

    def test_simple_planning_catastrophic_first_stop(self) -> None:
        loader = __import__("cerebra.cognition.cycle_config", fromlist=["CycleConfigLoader"]).CycleConfigLoader
        cfg = loader().load("simple.planning.v0")
        engine = ClutchEngine(cfg)

        ctx = _ctx(step_index=0, step_count=5, composite_score=0.2)
        d = engine.decide(ctx)
        assert d.action == "stop"
