"""Phase 7 gate types — ProposedAction and GateDecision."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProposedAction:
    """An action the cycle runtime is about to take, pending gate approval."""

    action_name: str  # maps to LeewayRule.capability
    session_id: str
    cycle_id: str
    step_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateDecision:
    """Result of LeewayPreActionGate.evaluate()."""

    final_decision: str  # "permitted" | "forbidden" | "requires_review"
    proposed_action: ProposedAction
    grants_applied: list[str]  # rule_ids of leeway rules that granted permission
    forbidden_by: str | None = None  # rule_id or "no_grants" if forbidden
    review_required_by: list[str] = field(default_factory=list)
