# SPDX-License-Identifier: Apache-2.0
"""Unit tests for governance rule schemas and loaders."""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.governance.defaults import DEFAULT_CONSTITUTIONAL_RULES, DEFAULT_LEEWAY_RULES
from cerebra.governance.models import LeewayRule, SignalCondition


@pytest.mark.unit
class TestLeewayRuleEvaluation:
    def test_unconditional_grant_always_applies(self) -> None:
        rule = DEFAULT_LEEWAY_RULES[0]  # LR-001: retrieve_from_memory
        assert rule.capability == "retrieve_from_memory"
        assert rule.is_granted({}) is True

    def test_conditional_grant_with_matching_signals(self) -> None:
        # LR-006: mutate_strategy_weights requires failure_streak >= 2 AND trajectory == "degrading"
        rule = next(r for r in DEFAULT_LEEWAY_RULES if r.rule_id == "LR-006")
        signals = {"failure_streak": 3, "trajectory": "degrading"}
        assert rule.is_granted(signals) is True

    def test_conditional_grant_fails_when_signals_dont_match(self) -> None:
        rule = next(r for r in DEFAULT_LEEWAY_RULES if r.rule_id == "LR-006")
        signals = {"failure_streak": 1, "trajectory": "flat"}
        assert rule.is_granted(signals) is False

    def test_and_join_requires_all_conditions(self) -> None:
        rule = LeewayRule(
            rule_id="test",
            capability="test_cap",
            conditions=[
                SignalCondition("a", ">=", 5),
                SignalCondition("b", "==", True),
            ],
            condition_join="AND",
            scope="persistent",
            phase="pre_action",
            reason="test",
        )
        assert rule.is_granted({"a": 5, "b": True}) is True
        assert rule.is_granted({"a": 5, "b": False}) is False
        assert rule.is_granted({"a": 4, "b": True}) is False

    def test_or_join_requires_any_condition(self) -> None:
        rule = LeewayRule(
            rule_id="test",
            capability="test_cap",
            conditions=[
                SignalCondition("a", ">=", 5),
                SignalCondition("b", "==", True),
            ],
            condition_join="OR",
            scope="persistent",
            phase="pre_action",
            reason="test",
        )
        assert rule.is_granted({"a": 10, "b": False}) is True
        assert rule.is_granted({"a": 0, "b": True}) is True
        assert rule.is_granted({"a": 0, "b": False}) is False

    def test_revocation_fires_when_signal_matches(self) -> None:
        rule = next(r for r in DEFAULT_LEEWAY_RULES if r.rule_id == "LR-005")
        # revocation: token_budget_exhausted == True
        assert rule.is_revoked({"token_budget_exhausted": True}) is True
        assert rule.is_revoked({"token_budget_exhausted": False}) is False

    def test_unknown_signal_raises_key_error(self) -> None:
        cond = SignalCondition("nonexistent_signal", "==", True)
        with pytest.raises(KeyError, match="nonexistent_signal"):
            cond.evaluate({})

    def test_all_ops(self) -> None:
        ops_and_expected = [
            (SignalCondition("x", ">=", 5), {"x": 5}, True),
            (SignalCondition("x", ">=", 5), {"x": 4}, False),
            (SignalCondition("x", "<=", 5), {"x": 5}, True),
            (SignalCondition("x", "<=", 5), {"x": 6}, False),
            (SignalCondition("x", ">", 5), {"x": 6}, True),
            (SignalCondition("x", ">", 5), {"x": 5}, False),
            (SignalCondition("x", "<", 5), {"x": 4}, True),
            (SignalCondition("x", "<", 5), {"x": 5}, False),
            (SignalCondition("x", "==", "foo"), {"x": "foo"}, True),
            (SignalCondition("x", "!=", "foo"), {"x": "bar"}, True),
            (SignalCondition("x", "in", ["a", "b"]), {"x": "a"}, True),
            (SignalCondition("x", "in", ["a", "b"]), {"x": "c"}, False),
        ]
        for cond, signals, expected in ops_and_expected:
            assert cond.evaluate(signals) is expected


@pytest.mark.unit
class TestDefaultRuleSets:
    def test_exactly_15_leeway_rules(self) -> None:
        assert len(DEFAULT_LEEWAY_RULES) == 15

    def test_exactly_5_constitutional_rules(self) -> None:
        assert len(DEFAULT_CONSTITUTIONAL_RULES) == 5

    def test_leeway_rule_ids_are_unique(self) -> None:
        ids = [r.rule_id for r in DEFAULT_LEEWAY_RULES]
        assert len(ids) == len(set(ids))

    def test_constitutional_rule_ids_are_unique(self) -> None:
        ids = [r.rule_id for r in DEFAULT_CONSTITUTIONAL_RULES]
        assert len(ids) == len(set(ids))

    def test_all_constitutional_rules_are_inviolable(self) -> None:
        assert all(r.is_inviolable for r in DEFAULT_CONSTITUTIONAL_RULES)

    def test_all_leeway_rules_have_valid_phases(self) -> None:
        valid_phases = {"pre_action", "post_action", "both"}
        for r in DEFAULT_LEEWAY_RULES:
            assert r.phase in valid_phases, f"{r.rule_id} has invalid phase {r.phase}"

    def test_all_leeway_rules_have_valid_scopes(self) -> None:
        valid_scopes = {"current_step", "current_cycle", "current_session", "persistent"}
        for r in DEFAULT_LEEWAY_RULES:
            assert r.scope in valid_scopes, f"{r.rule_id} has invalid scope {r.scope}"


@pytest.mark.unit
class TestGovernanceLoader:
    def test_write_and_reload_leeway_rules(self, tmp_path: Path) -> None:
        from cerebra.governance.loader import load_leeway_rules, write_defaults_to_vault

        write_defaults_to_vault(tmp_path)
        reloaded = load_leeway_rules(tmp_path / "leeway")
        assert len(reloaded) == 15
        assert reloaded[0].capability == "retrieve_from_memory"

    def test_write_and_reload_constitutional_rules(self, tmp_path: Path) -> None:
        from cerebra.governance.loader import (
            load_constitutional_rules,
            write_defaults_to_vault,
        )

        write_defaults_to_vault(tmp_path)
        reloaded = load_constitutional_rules(tmp_path / "constitutional")
        assert len(reloaded) == 5
        assert all(r.is_inviolable for r in reloaded)

    def test_round_trip_preserves_conditions(self, tmp_path: Path) -> None:
        from cerebra.governance.loader import load_leeway_rules, write_defaults_to_vault

        write_defaults_to_vault(tmp_path)
        reloaded = load_leeway_rules(tmp_path / "leeway")
        lr006 = next(r for r in reloaded if r.rule_id == "LR-006")
        assert len(lr006.conditions) == 2
        signals = {"failure_streak": 3, "trajectory": "degrading"}
        assert lr006.is_granted(signals) is True
