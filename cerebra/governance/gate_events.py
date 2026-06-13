"""Phase 7 — LeewayGrantApplied event emission helper."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cerebra.cognition.event_emitter import EventEmitter
    from cerebra.governance.types import GateDecision


def _now_ms() -> int:
    return int(time.time() * 1000)


def emit_leeway_grant_applied(
    emitter: EventEmitter,
    gate_decision: GateDecision,
    triggering_event_id: bytes,
    proposed_at_ms: int | None = None,
) -> bytes:
    """Emit LeewayGrantApplied event and return its event ID.

    MUST be called BEFORE emitting the gated action event. The action event's
    causation_id should be the bytes returned here.

    Args:
        emitter: EventEmitter for the current cycle stream.
        gate_decision: result of LeewayPreActionGate.evaluate().
        triggering_event_id: the event that triggered the action proposal
            (typically ClutchDecisionMade or CatalystArmSelected).
        proposed_at_ms: timestamp of action proposal; defaults to now.
    """
    action = gate_decision.proposed_action
    payload: dict[str, object] = {
        "session_id": action.session_id,
        "cycle_id": action.cycle_id,
        "step_id": action.step_id,
        "proposed_action": action.action_name,
        "grants_applied": gate_decision.grants_applied,
        "final_decision": gate_decision.final_decision,
        "applied_at": proposed_at_ms if proposed_at_ms is not None else _now_ms(),
    }
    if gate_decision.forbidden_by is not None:
        payload["forbidden_by"] = gate_decision.forbidden_by
    if gate_decision.review_required_by:
        payload["review_required_by"] = gate_decision.review_required_by

    return emitter.emit_cycle_event(
        event_type="LeewayGrantApplied",
        payload=payload,
        causation_id=triggering_event_id,
        indexed_tags={
            "session_id": action.session_id,
            "cycle_id": action.cycle_id,
            "step_id": action.step_id,
            "final_decision": gate_decision.final_decision,
        },
    )
