"""Phase 8 minimal Clutch stub — replaced by full ClutchEngine in Phase 9.

BUILTIN_PREDICATES: dict of name → callable(ClutchContext, params) → bool
ClutchStubEngine: evaluates rules in order, first match wins, defaults to accept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from cerebra.cognition.cycle_config import CycleConfig


@dataclass(frozen=True)
class ClutchContext:
    """Runtime context passed to each predicate during Clutch evaluation."""

    step_index: int        # 0-based position in cycle config's steps list
    step_count: int        # total steps defined in the cycle config
    composite_score: float # 0.0 to 1.0 from EvaluationComposer
    last_clutch_action: str | None
    total_steps_run: int   # total LLM executions so far in this cycle


@dataclass(frozen=True)
class ClutchDecision:
    """Result of ClutchStubEngine.decide()."""

    action: str        # one of CLUTCH_ACTIONS
    rule_matched: str  # name of the rule that fired (or "default_no_match")
    escalate_to_catalyst: bool = False  # always False in Phase 8 stub


# ── Built-in predicates ───────────────────────────────────────────────────────

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


BUILTIN_PREDICATES: dict[str, Callable[[ClutchContext, dict[str, Any]], bool]] = {
    "at_terminal_step": _at_terminal_step,
    "composite_below_threshold": _composite_below_threshold,
    "composite_above_threshold": _composite_above_threshold,
    "first_step": _first_step,
    "step_index_at": _step_index_at,
    "always": _always,
}


# ── Engine ────────────────────────────────────────────────────────────────────


class ClutchStubEngine:
    """Phase 8 minimal Clutch. Replaced by full ClutchEngine in Phase 9.

    Evaluates rules in config order. First matching predicate wins.
    Defaults to accept if no rule matches.
    """

    def __init__(self, cycle_config: "CycleConfig") -> None:
        self.rules = cycle_config.clutch_rules

    def decide(self, context: ClutchContext) -> ClutchDecision:
        for rule in self.rules:
            predicate = BUILTIN_PREDICATES[rule.predicate_name]
            if predicate(context, rule.parameters):
                return ClutchDecision(
                    action=rule.action,
                    rule_matched=rule.name,
                )
        return ClutchDecision(action="accept", rule_matched="default_no_match")
