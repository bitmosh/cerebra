"""Phase 9 Step 1 — Full ClutchEngine.

Renamed from clutch_stub.py (Phase 8). ClutchStubEngine renamed to ClutchEngine.
BUILTIN_PREDICATES expanded from 6 to 14 (7 new state-aware predicates + catalyst placeholder).
cascade_depth added to ClutchDecision; escalate_to_catalyst fires when no rule matches.

New predicates require ClutchContext.evaluation, .outcome, .cycle_state, .cycle_config
(all optional — existing callers that omit them receive graceful False returns).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cerebra.cognition.cycle_config import CycleConfig
    from cerebra.cognition.evaluation import EvaluationPacket
    from cerebra.cognition.predictions import OutcomeRecord


# ── ClutchDecision ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClutchDecision:
    """Result of ClutchEngine.decide()."""

    action: str        # one of CLUTCH_ACTIONS
    rule_matched: str  # name of the rule that fired (or "default_no_match")
    escalate_to_catalyst: bool = False  # True when no rule matches (Step 2 wires actual invocation)
    cascade_depth: int = 0             # 0-indexed position of the matching rule in the cascade


# ── ClutchCycleState ──────────────────────────────────────────────────────────


@dataclass
class ClutchCycleState:
    """Mutable state accumulated across cycle steps, passed to ClutchContext each step."""

    consecutive_steps_below_floor: int = 0
    prior_clutch_decisions: list[ClutchDecision] = field(default_factory=list)
    catalyst_invoked_this_step: bool = False


# ── ClutchContext ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClutchContext:
    """Runtime context passed to each predicate during ClutchEngine evaluation."""

    step_index: int         # 0-based position in cycle config's steps list
    step_count: int         # total steps defined in the cycle config
    composite_score: float  # 0.0 to 1.0 from EvaluationComposer
    last_clutch_action: str | None
    total_steps_run: int    # total LLM executions so far in this cycle
    # Phase 9 Step 1 additions — all optional for backward compat with existing tests:
    evaluation: EvaluationPacket | None = None   # per_signal_scores for signal_* predicates
    outcome: OutcomeRecord | None = None          # error_classification for prediction_* predicates
    cycle_state: ClutchCycleState = field(default_factory=ClutchCycleState)
    cycle_config: CycleConfig | None = None      # step name lookup for step_at predicate


# ── Built-in predicates (Phase 8 — 6) ────────────────────────────────────────


def _at_terminal_step(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if current step is the last in the config AND composite >= min_composite."""
    at_last = ctx.step_index == ctx.step_count - 1
    min_composite = float(params.get("min_composite", 0.0))
    return at_last and ctx.composite_score >= min_composite


def _composite_below_threshold(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if composite < threshold, with optional constraint on step position.

    params:
        threshold: float — required
        with_constraint: "first_step" — optional; if set, also requires step_index == 0
    """
    threshold = float(params["threshold"])
    below = ctx.composite_score < threshold
    constraint = params.get("with_constraint")
    if constraint == "first_step":
        return below and ctx.step_index == 0
    return below


def _composite_above_threshold(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if composite >= threshold."""
    return ctx.composite_score >= float(params["threshold"])


def _first_step(ctx: ClutchContext, _params: dict[str, Any]) -> bool:
    return ctx.step_index == 0


def _step_index_at(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    return ctx.step_index == int(params["index"])


def _always(_ctx: ClutchContext, _params: dict[str, Any]) -> bool:
    return True


# ── New state-aware predicates (Phase 9 Step 1 — 7 + 1 placeholder) ──────────


def _prediction_severe_miss(ctx: ClutchContext, _params: dict[str, Any]) -> bool:
    """True if prediction error classification is 'severe'."""
    if ctx.outcome is None:
        return False
    return ctx.outcome.error_classification == "severe"


def _prediction_notable_miss(ctx: ClutchContext, _params: dict[str, Any]) -> bool:
    """True if prediction error classification is 'notable' or 'severe'."""
    if ctx.outcome is None:
        return False
    return ctx.outcome.error_classification in ("notable", "severe")


def _signal_below_threshold(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if a specific signal score < threshold.

    params: {"signal": "COHERENCE", "threshold": 0.5}
    Returns False if evaluation not available or signal not scored.
    """
    if ctx.evaluation is None:
        return False
    signal_name = params["signal"]
    threshold = float(params["threshold"])
    score = ctx.evaluation.per_signal_scores.get(signal_name)
    if score is None:
        return False
    return score < threshold


def _signal_above_threshold(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if a specific signal score >= threshold.

    params: {"signal": "COHERENCE", "threshold": 0.7}
    Returns False if evaluation not available or signal not scored.
    """
    if ctx.evaluation is None:
        return False
    signal_name = params["signal"]
    threshold = float(params["threshold"])
    score = ctx.evaluation.per_signal_scores.get(signal_name)
    if score is None:
        return False
    return score >= threshold


def _consecutive_steps_below_floor(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if N or more consecutive prior steps had composite below cycle floor.

    params: {"count": 2}
    Reads ctx.cycle_state.consecutive_steps_below_floor.
    """
    return ctx.cycle_state.consecutive_steps_below_floor >= int(params["count"])


def _prior_step_action_was(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if the immediately prior step's Clutch action was params['action'].

    params: {"action": "refine"}
    Returns False if no prior step (first step in cycle).
    """
    if not ctx.cycle_state.prior_clutch_decisions:
        return False
    return ctx.cycle_state.prior_clutch_decisions[-1].action == params["action"]


def _step_at(ctx: ClutchContext, params: dict[str, Any]) -> bool:
    """True if current step name matches params['step_name'].

    params: {"step_name": "critique_plan"}
    Returns False if cycle_config not available or step_index out of bounds.
    """
    if ctx.cycle_config is None:
        return False
    steps = ctx.cycle_config.steps
    if ctx.step_index < 0 or ctx.step_index >= len(steps):
        return False
    return steps[ctx.step_index].name == params["step_name"]


def _catalyst_was_invoked(ctx: ClutchContext, _params: dict[str, Any]) -> bool:
    """True if catalyst was invoked on the immediately prior step."""
    return ctx.cycle_state.catalyst_invoked_this_step


# ── BUILTIN_PREDICATES registry ───────────────────────────────────────────────


BUILTIN_PREDICATES: dict[str, Callable[[ClutchContext, dict[str, Any]], bool]] = {
    # Phase 8 originals
    "at_terminal_step": _at_terminal_step,
    "composite_below_threshold": _composite_below_threshold,
    "composite_above_threshold": _composite_above_threshold,
    "first_step": _first_step,
    "step_index_at": _step_index_at,
    "always": _always,
    # Phase 9 Step 1 additions
    "prediction_severe_miss": _prediction_severe_miss,
    "prediction_notable_miss": _prediction_notable_miss,
    "signal_below_threshold": _signal_below_threshold,
    "signal_above_threshold": _signal_above_threshold,
    "consecutive_steps_below_floor": _consecutive_steps_below_floor,
    "prior_step_action_was": _prior_step_action_was,
    "step_at": _step_at,
    "catalyst_was_invoked": _catalyst_was_invoked,
}


# ── ClutchEngine ──────────────────────────────────────────────────────────────


class ClutchEngine:
    """Production Clutch engine (Phase 9+). Renamed from ClutchStubEngine (Phase 8).

    Evaluates rules in config order (first match wins). Records cascade_depth
    (which rule index fired, 0-indexed). Sets escalate_to_catalyst=True when no
    rule matches — Step 2 implements actual catalyst invocation.
    """

    def __init__(self, cycle_config: CycleConfig) -> None:
        self.rules = cycle_config.clutch_rules
        self._predicates = BUILTIN_PREDICATES

    def decide(self, context: ClutchContext) -> ClutchDecision:
        for idx, rule in enumerate(self.rules):
            predicate = self._predicates[rule.predicate_name]
            if predicate(context, rule.parameters):
                return ClutchDecision(
                    action=rule.action,
                    rule_matched=rule.name,
                    cascade_depth=idx,
                    escalate_to_catalyst=False,
                )
        # No rule matched — set escalation flag; safe default action is "accept"
        return ClutchDecision(
            action="accept",
            rule_matched="default_no_match",
            cascade_depth=len(self.rules),
            escalate_to_catalyst=True,
        )
