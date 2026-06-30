"""Tests for LeewayPreActionGate.evaluate()."""

from __future__ import annotations

import pytest

from cerebra.governance.models import ConstitutionalRule, LeewayRule
from cerebra.governance.pre_action_gate import LeewayPreActionGate
from cerebra.governance.types import ProposedAction

# ── helpers ───────────────────────────────────────────────────────────────────


def _action(name: str = "retrieve_from_memory") -> ProposedAction:
    return ProposedAction(
        action_name=name,
        session_id="sess_001",
        cycle_id="cycle_001",
        step_id="step_001",
    )


def _leeway(capability: str, phase: str = "pre_action") -> LeewayRule:
    return LeewayRule(
        rule_id=f"LR-test-{capability[:8]}",
        capability=capability,
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase=phase,  # type: ignore[arg-type]
        reason="test rule",
    )


def _constitutional(rule_id: str = "CONST-test") -> ConstitutionalRule:
    return ConstitutionalRule(
        rule_id=rule_id,
        description="test constitutional rule",
        revokes_leeway_when=[],
        applies_to="all_capabilities",
    )


# ── LeewayRule.grants() predicate ────────────────────────────────────────────


@pytest.mark.unit
class TestLeewayRuleGrantsPredicate:
    def test_grants_matching_capability_pre_action(self) -> None:
        rule = _leeway("retrieve_from_memory", "pre_action")
        action = _action("retrieve_from_memory")
        assert rule.grants(action) is True

    def test_grants_matching_capability_both_phase(self) -> None:
        rule = _leeway("write_to_semantic_memory", "both")
        action = _action("write_to_semantic_memory")
        assert rule.grants(action) is True

    def test_does_not_grant_post_action_phase(self) -> None:
        rule = _leeway("retrieve_from_memory", "post_action")
        action = _action("retrieve_from_memory")
        assert rule.grants(action) is False

    def test_does_not_grant_different_capability(self) -> None:
        rule = _leeway("retrieve_from_memory")
        action = _action("spawn_continuation_bundle")
        assert rule.grants(action) is False

    def test_does_not_grant_partial_capability_match(self) -> None:
        rule = _leeway("retrieve")
        action = _action("retrieve_from_memory")
        assert rule.grants(action) is False


# ── ConstitutionalRule.forbids() no-op (DEV-009) ─────────────────────────────


@pytest.mark.unit
class TestConstitutionalRuleForbidsNoOp:
    def test_forbids_always_returns_false(self) -> None:
        """DEV-009: constitutional forbids are a no-op in v0.1."""
        rule = _constitutional()
        action = _action("retrieve_from_memory")
        assert rule.forbids(action) is False

    def test_forbids_false_for_any_action(self) -> None:
        rule = _constitutional()
        for capability in ["tombstone_memory", "mutate_strategy_weights", "end_cycle"]:
            assert rule.forbids(_action(capability)) is False

    def test_forbids_false_even_with_applies_to_match(self) -> None:
        rule = ConstitutionalRule(
            rule_id="CONST-specific",
            description="targets tombstone_memory",
            revokes_leeway_when=[],
            applies_to="tombstone_memory",
            is_inviolable=True,
        )
        assert rule.forbids(_action("tombstone_memory")) is False


# ── LeewayPreActionGate.evaluate() ───────────────────────────────────────────


@pytest.mark.unit
class TestLeewayPreActionGateEvaluate:
    def test_empty_leeway_rules_returns_forbidden_no_grants(self) -> None:
        gate = LeewayPreActionGate(leeway_rules=[], constitutional_rules=[])
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "forbidden"
        assert decision.forbidden_by == "no_grants"
        assert decision.grants_applied == []

    def test_empty_leeway_with_constitutional_still_no_grants(self) -> None:
        gate = LeewayPreActionGate(
            leeway_rules=[],
            constitutional_rules=[_constitutional()],
        )
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "forbidden"
        assert decision.forbidden_by == "no_grants"

    def test_single_granting_rule_returns_permitted(self) -> None:
        rule = _leeway("retrieve_from_memory")
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "permitted"
        assert rule.rule_id in decision.grants_applied
        assert decision.forbidden_by is None

    def test_multiple_matching_rules_all_applied(self) -> None:
        rule_a = LeewayRule(
            rule_id="LR-A",
            capability="retrieve_from_memory",
            conditions=[],
            condition_join="AND",
            scope="persistent",
            phase="pre_action",
            reason="test A",
        )
        rule_b = LeewayRule(
            rule_id="LR-B",
            capability="retrieve_from_memory",
            conditions=[],
            condition_join="AND",
            scope="current_session",
            phase="pre_action",
            reason="test B",
        )
        gate = LeewayPreActionGate(leeway_rules=[rule_a, rule_b], constitutional_rules=[])
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "permitted"
        assert "LR-A" in decision.grants_applied
        assert "LR-B" in decision.grants_applied

    def test_composition_by_union_one_of_two_grants(self) -> None:
        rule_match = _leeway("retrieve_from_memory")
        rule_other = _leeway("end_cycle")
        gate = LeewayPreActionGate(
            leeway_rules=[rule_match, rule_other],
            constitutional_rules=[],
        )
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "permitted"
        assert rule_match.rule_id in decision.grants_applied
        assert rule_other.rule_id not in decision.grants_applied

    def test_no_matching_rule_returns_forbidden(self) -> None:
        gate = LeewayPreActionGate(
            leeway_rules=[_leeway("end_cycle")],
            constitutional_rules=[],
        )
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "forbidden"
        assert decision.forbidden_by == "no_grants"

    def test_constitutional_rules_do_not_forbid_in_v0_1(self) -> None:
        """DEV-009: constitutional rules present but gate still permits matching capability."""
        c_rules = [_constitutional("CONST-A"), _constitutional("CONST-B")]
        l_rules = [_leeway("retrieve_from_memory")]
        gate = LeewayPreActionGate(leeway_rules=l_rules, constitutional_rules=c_rules)
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "permitted"

    def test_constitutional_rules_all_loaded_from_defaults_do_not_forbid(self) -> None:
        """DEV-009: full default constitutional rules don't block any action."""
        from cerebra.governance.defaults import (
            DEFAULT_CONSTITUTIONAL_RULES,
            DEFAULT_LEEWAY_RULES,
        )

        gate = LeewayPreActionGate(
            leeway_rules=DEFAULT_LEEWAY_RULES,
            constitutional_rules=DEFAULT_CONSTITUTIONAL_RULES,
        )
        # All default capabilities should be permitted via their baseline grants
        for cap in [
            "retrieve_from_memory",
            "build_context_packet",
            "evaluate_signals",
            "issue_clutch_decision",
        ]:
            decision = gate.evaluate(_action(cap))
            assert decision.final_decision == "permitted", f"Expected permitted for {cap}"

    def test_review_required_by_always_empty_in_v0_1(self) -> None:
        """DEV-010: requires_review path not implemented; field stays empty list."""
        rule = _leeway("retrieve_from_memory")
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.review_required_by == []

    def test_forbidden_decision_carries_proposed_action(self) -> None:
        gate = LeewayPreActionGate(leeway_rules=[], constitutional_rules=[])
        action = _action("spawn_continuation_bundle")
        decision = gate.evaluate(action)
        assert decision.proposed_action is action

    def test_permitted_decision_carries_proposed_action(self) -> None:
        rule = _leeway("end_cycle")
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        action = _action("end_cycle")
        decision = gate.evaluate(action)
        assert decision.proposed_action is action

    def test_post_action_only_rule_does_not_grant(self) -> None:
        rule = _leeway("retrieve_from_memory", "post_action")
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "forbidden"
        assert decision.forbidden_by == "no_grants"

    def test_both_phase_rule_grants_pre_action(self) -> None:
        rule = _leeway("write_to_semantic_memory", "both")
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        decision = gate.evaluate(_action("write_to_semantic_memory"))
        assert decision.final_decision == "permitted"

    def test_unknown_action_name_returns_forbidden(self) -> None:
        rule = _leeway("retrieve_from_memory")
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        decision = gate.evaluate(_action("nonexistent_action"))
        assert decision.final_decision == "forbidden"

    def test_default_leeway_rules_permit_baseline_capabilities(self) -> None:
        from cerebra.governance.defaults import DEFAULT_LEEWAY_RULES

        gate = LeewayPreActionGate(leeway_rules=DEFAULT_LEEWAY_RULES, constitutional_rules=[])
        for cap in [
            "retrieve_from_memory",
            "build_context_packet",
            "evaluate_signals",
            "issue_clutch_decision",
            "consolidate_memory",
            "write_to_episodic_memory",
            "emit_graph_event",
            "ask_user",
            "end_cycle",
        ]:
            d = gate.evaluate(_action(cap))
            assert d.final_decision == "permitted", f"Expected permitted for {cap}"

    def test_grants_applied_uses_rule_ids(self) -> None:
        rule = LeewayRule(
            rule_id="LR-sentinel",
            capability="ask_user",
            conditions=[],
            condition_join="AND",
            scope="persistent",
            phase="pre_action",
            reason="sentinel",
        )
        gate = LeewayPreActionGate(leeway_rules=[rule], constitutional_rules=[])
        decision = gate.evaluate(_action("ask_user"))
        assert "LR-sentinel" in decision.grants_applied
