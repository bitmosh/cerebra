# SPDX-License-Identifier: Apache-2.0
"""ReinjectionTriggerEvaluator — Phase 9 Step 4.

Evaluates whether a terminated cycle should spawn a child session for
continuation. Runs once per cycle after termination; distinct from Clutch
(which runs per-step within the cycle).

v0.1 ships one predicate: max_steps_without_acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cerebra.cognition._constants import BUILTIN_REINJECTION_PREDICATE_NAMES

# ── ReinjectionDecision ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReinjectionDecision:
    """Outcome of trigger evaluation."""

    should_fire: bool
    trigger_name: str | None = None
    predicate: str | None = None
    blocked_reason: str | None = None

    @classmethod
    def fire(cls, trigger_name: str, predicate: str) -> ReinjectionDecision:
        return cls(should_fire=True, trigger_name=trigger_name, predicate=predicate)

    @classmethod
    def no_match(cls) -> ReinjectionDecision:
        return cls(should_fire=False)

    @classmethod
    def blocked(cls, reason: str) -> ReinjectionDecision:
        return cls(should_fire=False, blocked_reason=reason)


# ── Builtin predicates ────────────────────────────────────────────────────────


def _pred_max_steps_without_acceptance(
    termination_reason: str,
    step_history: list[Any],
    parameters: dict[str, Any],
) -> bool:
    """Fire when the cycle hit the step cap with no accepted step.

    Accepts any list of objects with a .clutch_action attribute (StepResult).
    """
    if termination_reason != "cap_reached":
        return False
    return not any(getattr(step, "clutch_action", None) == "accept" for step in step_history)


BUILTIN_REINJECTION_PREDICATES: dict[str, Any] = {
    "max_steps_without_acceptance": _pred_max_steps_without_acceptance,
}

assert (
    frozenset(BUILTIN_REINJECTION_PREDICATES.keys()) == BUILTIN_REINJECTION_PREDICATE_NAMES
), "BUILTIN_REINJECTION_PREDICATES keys must match BUILTIN_REINJECTION_PREDICATE_NAMES"


# ── ReinjectionTriggerEvaluator ───────────────────────────────────────────────


class ReinjectionTriggerEvaluator:
    """Evaluates whether a terminated cycle should spawn a child session.

    Receives the cycle's termination reason and step history; returns a
    ReinjectionDecision. Blocked when max_recursion_depth is reached.
    """

    def __init__(self, triggers: list[Any]) -> None:
        # triggers: list[ReinjectionTrigger] — duck-typed to avoid circular import
        self._triggers = triggers

    def evaluate(
        self,
        termination_reason: str,
        step_history: list[Any],
        recursion_depth: int,
        max_recursion_depth: int,
    ) -> ReinjectionDecision:
        """Evaluate all configured triggers against cycle termination state."""
        if not self._triggers:
            return ReinjectionDecision.no_match()

        if max_recursion_depth <= 0 or recursion_depth >= max_recursion_depth:
            return ReinjectionDecision.blocked(reason="max_recursion_reached")

        for trigger in self._triggers:
            predicate_fn = BUILTIN_REINJECTION_PREDICATES.get(trigger.predicate)
            if predicate_fn is None:
                continue
            if predicate_fn(termination_reason, step_history, trigger.parameters):
                return ReinjectionDecision.fire(
                    trigger_name=trigger.name,
                    predicate=trigger.predicate,
                )

        return ReinjectionDecision.no_match()
