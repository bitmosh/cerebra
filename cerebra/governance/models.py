# SPDX-License-Identifier: Apache-2.0
"""
Governance data models — schemas for constitutional and leeway rules.

Faithfully implements the schemas in CEREBRA_LEEWAY_NETWORK.md §5 and §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from cerebra.governance.types import ProposedAction

# ── Leeway rules ─────────────────────────────────────────────────────────────

ConditionOp = Literal[">=", "<=", ">", "<", "==", "!=", "in"]
ConditionJoin = Literal["AND", "OR"]
LeewayScope = Literal["current_step", "current_cycle", "current_session", "persistent"]
LeewayPhase = Literal["pre_action", "post_action", "both"]


@dataclass
class SignalCondition:
    signal: str
    op: ConditionOp
    value: Any

    def evaluate(self, signals: dict[str, Any]) -> bool:
        if self.signal not in signals:
            raise KeyError(f"Unknown signal '{self.signal}' in leeway condition")
        actual = signals[self.signal]
        match self.op:
            case ">=":
                return bool(actual >= self.value)
            case "<=":
                return bool(actual <= self.value)
            case ">":
                return bool(actual > self.value)
            case "<":
                return bool(actual < self.value)
            case "==":
                return bool(actual == self.value)
            case "!=":
                return bool(actual != self.value)
            case "in":
                return bool(actual in self.value)
            case _:
                raise ValueError(f"Unknown op '{self.op}'")


@dataclass
class LeewayRule:
    rule_id: str
    capability: str
    conditions: list[SignalCondition]
    condition_join: ConditionJoin
    scope: LeewayScope
    phase: LeewayPhase
    reason: str
    schema_version: int = 1
    override_priority: int = 0
    revocation_conditions: list[SignalCondition] = field(default_factory=list)
    created_at: int = 0
    created_by: str = "system_default"

    def is_granted(self, signals: dict[str, Any]) -> bool:
        """Evaluate all conditions against signals; return True if grant applies."""
        if not self.conditions:
            return True  # baseline (unconditional) grant
        results = [c.evaluate(signals) for c in self.conditions]
        if self.condition_join == "AND":
            return all(results)
        return any(results)

    def is_revoked(self, signals: dict[str, Any]) -> bool:
        """Return True if any revocation condition fires."""
        return any(c.evaluate(signals) for c in self.revocation_conditions)

    def grants(self, action: ProposedAction) -> bool:
        """Return True if this rule grants permission for the proposed action.

        v0.1: action-name + phase matching only. Signal-based conditions (is_granted)
        are consulted in v0.2 once the signals dict is available at gate call time.
        """
        return self.capability == action.action_name and self.phase in ("pre_action", "both")


# ── Constitutional rules ──────────────────────────────────────────────────────


@dataclass
class RevocationTrigger:
    """A trigger condition that revokes leeway grants."""

    field: str  # e.g. "output_topic_in", "output_contains_claim"
    value: Any


@dataclass
class ConstitutionalRule:
    rule_id: str
    description: str
    revokes_leeway_when: list[RevocationTrigger]
    applies_to: str  # "all_capabilities" or specific capability
    is_inviolable: bool = True
    created_at: int = 0

    def forbids(self, _action: ProposedAction) -> bool:
        """Return True if this constitutional rule pre-emptively forbids the action.

        v0.1: always returns False — DEV-009. Existing constitutional rules are
        post-action output analyzers, not pre-action capability blockers. A dedicated
        pre-action rule shape is a v0.2 design task.
        """
        return False
