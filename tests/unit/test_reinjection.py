"""Unit tests for ReinjectionTriggerEvaluator — Phase 9 Step 4."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cerebra.cognition.cycle_config import ReinjectionTrigger
from cerebra.cognition.reinjection import (
    BUILTIN_REINJECTION_PREDICATES,
    ReinjectionDecision,
    ReinjectionTriggerEvaluator,
    _pred_max_steps_without_acceptance,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _step(clutch_action: str) -> SimpleNamespace:
    return SimpleNamespace(clutch_action=clutch_action)


def _trigger(predicate: str = "max_steps_without_acceptance", name: str = "t1") -> ReinjectionTrigger:
    return ReinjectionTrigger(name=name, predicate=predicate, parameters={})


def _evaluator(triggers: list[ReinjectionTrigger] | None = None) -> ReinjectionTriggerEvaluator:
    return ReinjectionTriggerEvaluator(triggers or [_trigger()])


# ── ReinjectionDecision constructors ─────────────────────────────────────────


def test_decision_fire():
    d = ReinjectionDecision.fire("t1", "max_steps_without_acceptance")
    assert d.should_fire is True
    assert d.trigger_name == "t1"
    assert d.predicate == "max_steps_without_acceptance"
    assert d.blocked_reason is None


def test_decision_no_match():
    d = ReinjectionDecision.no_match()
    assert d.should_fire is False
    assert d.trigger_name is None
    assert d.blocked_reason is None


def test_decision_blocked():
    d = ReinjectionDecision.blocked("max_recursion_reached")
    assert d.should_fire is False
    assert d.blocked_reason == "max_recursion_reached"


# ── _pred_max_steps_without_acceptance ───────────────────────────────────────


def test_pred_fires_on_cap_reached_no_accept():
    history = [_step("refine"), _step("refine"), _step("refine")]
    assert _pred_max_steps_without_acceptance("cap_reached", history, {}) is True


def test_pred_does_not_fire_when_accept_in_history():
    history = [_step("refine"), _step("accept"), _step("refine")]
    assert _pred_max_steps_without_acceptance("cap_reached", history, {}) is False


def test_pred_does_not_fire_on_non_cap_reached():
    history = [_step("refine"), _step("refine")]
    assert _pred_max_steps_without_acceptance("accept", history, {}) is False
    assert _pred_max_steps_without_acceptance("stop", history, {}) is False
    assert _pred_max_steps_without_acceptance("error", history, {}) is False


def test_pred_fires_with_empty_history():
    # Empty history = no accept steps → fires when cap_reached
    assert _pred_max_steps_without_acceptance("cap_reached", [], {}) is True


def test_pred_does_not_fire_on_stop_even_without_accept():
    history = [_step("stop")]
    assert _pred_max_steps_without_acceptance("stop", history, {}) is False


# ── BUILTIN_REINJECTION_PREDICATES registry ───────────────────────────────────


def test_builtin_registry_has_max_steps():
    assert "max_steps_without_acceptance" in BUILTIN_REINJECTION_PREDICATES


def test_builtin_registry_callable():
    fn = BUILTIN_REINJECTION_PREDICATES["max_steps_without_acceptance"]
    assert callable(fn)
    assert fn("cap_reached", [], {}) is True


# ── ReinjectionTriggerEvaluator: empty triggers ───────────────────────────────


def test_evaluator_empty_triggers_returns_no_match():
    ev = ReinjectionTriggerEvaluator([])
    d = ev.evaluate("cap_reached", [], recursion_depth=0, max_recursion_depth=3)
    assert d.should_fire is False
    assert d.blocked_reason is None


# ── ReinjectionTriggerEvaluator: max_recursion_depth blocking ─────────────────


def test_evaluator_blocked_when_max_recursion_zero():
    ev = _evaluator()
    d = ev.evaluate("cap_reached", [], recursion_depth=0, max_recursion_depth=0)
    assert d.should_fire is False
    assert d.blocked_reason == "max_recursion_reached"


def test_evaluator_blocked_when_depth_equals_max():
    ev = _evaluator()
    d = ev.evaluate("cap_reached", [], recursion_depth=3, max_recursion_depth=3)
    assert d.should_fire is False
    assert d.blocked_reason == "max_recursion_reached"


def test_evaluator_blocked_when_depth_exceeds_max():
    ev = _evaluator()
    d = ev.evaluate("cap_reached", [], recursion_depth=5, max_recursion_depth=3)
    assert d.should_fire is False
    assert d.blocked_reason == "max_recursion_reached"


def test_evaluator_not_blocked_just_below_max():
    ev = _evaluator()
    d = ev.evaluate(
        "cap_reached",
        [_step("refine")],
        recursion_depth=2,
        max_recursion_depth=3,
    )
    assert d.should_fire is True


# ── ReinjectionTriggerEvaluator: predicate matching ──────────────────────────


def test_evaluator_fires_when_predicate_matches():
    ev = _evaluator()
    d = ev.evaluate("cap_reached", [_step("refine")], recursion_depth=0, max_recursion_depth=3)
    assert d.should_fire is True
    assert d.predicate == "max_steps_without_acceptance"
    assert d.trigger_name == "t1"


def test_evaluator_no_match_when_predicate_does_not_fire():
    ev = _evaluator()
    # "accept" outcome: predicate won't fire
    d = ev.evaluate("accept", [_step("accept")], recursion_depth=0, max_recursion_depth=3)
    assert d.should_fire is False
    assert d.blocked_reason is None


def test_evaluator_skips_unknown_predicate_name():
    trigger = ReinjectionTrigger(name="bad", predicate="nonexistent_predicate", parameters={})
    ev = ReinjectionTriggerEvaluator([trigger])
    d = ev.evaluate("cap_reached", [], recursion_depth=0, max_recursion_depth=3)
    assert d.should_fire is False


def test_evaluator_first_matching_trigger_wins():
    t1 = ReinjectionTrigger(name="first", predicate="max_steps_without_acceptance", parameters={})
    t2 = ReinjectionTrigger(name="second", predicate="max_steps_without_acceptance", parameters={})
    ev = ReinjectionTriggerEvaluator([t1, t2])
    d = ev.evaluate("cap_reached", [], recursion_depth=0, max_recursion_depth=3)
    assert d.should_fire is True
    assert d.trigger_name == "first"


# ── CycleConfig integration: validates reinjection fields ─────────────────────


def test_cycle_config_loads_planning_adaptive_with_reinjection():
    from cerebra.cognition.cycle_config import CycleConfigLoader
    loader = CycleConfigLoader()
    config = loader.load("planning.adaptive.v0")
    assert len(config.reinjection_triggers) == 1
    assert config.reinjection_triggers[0].predicate == "max_steps_without_acceptance"
    assert config.max_recursion_depth == 3


def test_cycle_config_simple_planning_has_no_triggers():
    from cerebra.cognition.cycle_config import CycleConfigLoader
    loader = CycleConfigLoader()
    config = loader.load("simple.planning.v0")
    assert config.reinjection_triggers == []
    assert config.max_recursion_depth == 0


def test_cycle_config_rejects_unknown_reinjection_predicate():
    from cerebra.cognition.cycle_config import CycleConfigValidationError, _parse_config
    data = {
        "name": "test",
        "version": 1,
        "description": "",
        "max_steps": 5,
        "max_recursion_depth": 3,
        "steps": [{"name": "s1", "description": "", "prompt_template": {"template": "hi", "expected_output_format": "free_form"}}],
        "stop_conditions": [{"name": "sc", "type": "max_steps_reached", "parameters": {}}],
        "clutch_rules": [{"name": "r1", "description": "", "predicate_name": "at_terminal_step", "action": "accept", "parameters": {}}],
        "reinjection_triggers": [{"name": "bad", "predicate": "does_not_exist", "parameters": {}}],
    }
    with pytest.raises(CycleConfigValidationError, match="Unknown reinjection predicate"):
        _parse_config(data)


def test_cycle_config_rejects_triggers_with_zero_max_depth():
    from cerebra.cognition.cycle_config import CycleConfigValidationError, _parse_config
    data = {
        "name": "test",
        "version": 1,
        "description": "",
        "max_steps": 5,
        "max_recursion_depth": 0,
        "steps": [{"name": "s1", "description": "", "prompt_template": {"template": "hi", "expected_output_format": "free_form"}}],
        "stop_conditions": [{"name": "sc", "type": "max_steps_reached", "parameters": {}}],
        "clutch_rules": [{"name": "r1", "description": "", "predicate_name": "at_terminal_step", "action": "accept", "parameters": {}}],
        "reinjection_triggers": [{"name": "t1", "predicate": "max_steps_without_acceptance", "parameters": {}}],
    }
    with pytest.raises(CycleConfigValidationError, match="max_recursion_depth is 0"):
        _parse_config(data)


def test_cycle_config_rejects_negative_max_recursion_depth():
    from cerebra.cognition.cycle_config import CycleConfigValidationError, _parse_config
    data = {
        "name": "test",
        "version": 1,
        "description": "",
        "max_steps": 5,
        "max_recursion_depth": -1,
        "steps": [{"name": "s1", "description": "", "prompt_template": {"template": "hi", "expected_output_format": "free_form"}}],
        "stop_conditions": [{"name": "sc", "type": "max_steps_reached", "parameters": {}}],
        "clutch_rules": [{"name": "r1", "description": "", "predicate_name": "at_terminal_step", "action": "accept", "parameters": {}}],
    }
    with pytest.raises(CycleConfigValidationError, match="max_recursion_depth must be >= 0"):
        _parse_config(data)
