# SPDX-License-Identifier: Apache-2.0
"""Stop condition evaluator for the cycle runtime — Phase 8 Step 2.

StopConditionEvaluator.check(state) returns (should_stop, condition_name | None).
All five condition types defined in cycle_config_schema.md are handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cerebra.cognition.cycle_config import CycleConfig, StopCondition


@dataclass
class CycleState:
    """Snapshot of cycle execution state passed to StopConditionEvaluator."""

    steps_run: int
    all_steps_completed: bool
    recent_composites: list[float]  # all composite scores in execution order
    explicit_stop: bool  # set True when Clutch action was "stop"
    user_interrupted: bool  # set True on SIGINT/SIGTERM
    consecutive_low_composites: list[float] = field(default_factory=list)


class StopConditionEvaluator:
    """Evaluate all stop conditions against current cycle state.

    Returns on the FIRST condition that fires; evaluation order follows
    the config's stop_conditions list.
    """

    def __init__(self, config: CycleConfig) -> None:
        self.config = config

    def check(self, state: CycleState) -> tuple[bool, str | None]:
        """Return (should_stop, condition_name) or (False, None)."""
        for cond in self.config.stop_conditions:
            if self._evaluate(cond, state):
                return True, cond.name
        return False, None

    def _evaluate(self, cond: StopCondition, state: CycleState) -> bool:
        if cond.type == "max_steps_reached":
            return state.steps_run >= self.config.max_steps

        if cond.type == "all_steps_completed":
            return state.all_steps_completed

        if cond.type == "composite_floor_consecutive":
            threshold = float(cond.parameters.get("threshold", 0.30))
            count = int(cond.parameters.get("consecutive_count", 1))
            recent = state.recent_composites[-count:]
            return len(recent) >= count and all(c < threshold for c in recent)

        if cond.type == "explicit_clutch_stop":
            return state.explicit_stop

        if cond.type == "user_interrupt":
            return state.user_interrupted

        return False
