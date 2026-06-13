"""Tests for ProposedAction and GateDecision frozen dataclasses."""

from __future__ import annotations

import pytest

from cerebra.governance.types import GateDecision, ProposedAction


def _action(name: str = "retrieve_from_memory") -> ProposedAction:
    return ProposedAction(
        action_name=name,
        session_id="sess_001",
        cycle_id="cycle_001",
        step_id="step_001",
    )


def _permitted(action: ProposedAction | None = None) -> GateDecision:
    a = action or _action()
    return GateDecision(
        final_decision="permitted",
        proposed_action=a,
        grants_applied=["LR-001"],
    )


@pytest.mark.unit
class TestProposedActionType:
    def test_proposed_action_is_frozen(self) -> None:
        a = _action()
        with pytest.raises((AttributeError, TypeError)):
            a.action_name = "mutated"  # type: ignore[misc]

    def test_proposed_action_empty_payload_default(self) -> None:
        a = _action()
        assert a.payload == {}

    def test_proposed_action_with_payload(self) -> None:
        a = ProposedAction(
            action_name="spawn_continuation_bundle",
            session_id="s",
            cycle_id="c",
            step_id="step",
            payload={"reason": "stuck"},
        )
        assert a.payload["reason"] == "stuck"

    def test_proposed_action_payload_instances_independent(self) -> None:
        a1 = _action()
        a2 = _action()
        assert a1.payload is not a2.payload  # each instance gets its own dict


@pytest.mark.unit
class TestGateDecisionType:
    def test_gate_decision_is_frozen(self) -> None:
        d = _permitted()
        with pytest.raises((AttributeError, TypeError)):
            d.final_decision = "mutated"  # type: ignore[misc]

    def test_gate_decision_forbidden_by_defaults_none(self) -> None:
        d = _permitted()
        assert d.forbidden_by is None

    def test_gate_decision_review_required_by_defaults_empty(self) -> None:
        d = _permitted()
        assert d.review_required_by == []

    def test_gate_decision_review_required_instances_independent(self) -> None:
        d1 = _permitted()
        d2 = _permitted()
        assert d1.review_required_by is not d2.review_required_by

    def test_gate_decision_carries_proposed_action(self) -> None:
        a = _action("emit_graph_event")
        d = GateDecision(
            final_decision="permitted",
            proposed_action=a,
            grants_applied=["LR-013"],
        )
        assert d.proposed_action.action_name == "emit_graph_event"
