# SPDX-License-Identifier: Apache-2.0
"""Tests for load_pre_action_gate() loader helper."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cerebra.governance.defaults import DEFAULT_CONSTITUTIONAL_RULES, DEFAULT_LEEWAY_RULES
from cerebra.governance.loader import load_pre_action_gate, write_defaults_to_vault
from cerebra.governance.pre_action_gate import LeewayPreActionGate
from cerebra.governance.types import ProposedAction

# ── helpers ───────────────────────────────────────────────────────────────────


def _vault_with_defaults() -> Path:
    vault = Path(tempfile.mkdtemp())
    write_defaults_to_vault(vault)
    return vault


def _action(name: str) -> ProposedAction:
    return ProposedAction(
        action_name=name,
        session_id="sess_loader",
        cycle_id="cycle_loader",
        step_id="step_loader",
    )


# ── loader tests ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLoadPreActionGate:
    def test_returns_leeway_pre_action_gate_instance(self) -> None:
        vault = _vault_with_defaults()
        gate = load_pre_action_gate(vault)
        assert isinstance(gate, LeewayPreActionGate)

    def test_default_rules_loaded_from_vault(self) -> None:
        vault = _vault_with_defaults()
        gate = load_pre_action_gate(vault)
        assert len(gate.leeway_rules) == len(DEFAULT_LEEWAY_RULES)

    def test_default_constitutional_rules_loaded(self) -> None:
        vault = _vault_with_defaults()
        gate = load_pre_action_gate(vault)
        assert len(gate.constitutional_rules) == len(DEFAULT_CONSTITUTIONAL_RULES)

    def test_gate_permits_baseline_capability(self) -> None:
        vault = _vault_with_defaults()
        gate = load_pre_action_gate(vault)
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "permitted"

    def test_gate_forbids_unknown_capability(self) -> None:
        vault = _vault_with_defaults()
        gate = load_pre_action_gate(vault)
        decision = gate.evaluate(_action("nonexistent_capability_xyz"))
        assert decision.final_decision == "forbidden"
        assert decision.forbidden_by == "no_grants"

    def test_empty_vault_dirs_return_empty_rules(self) -> None:
        vault = Path(tempfile.mkdtemp())
        (vault / "leeway").mkdir()
        (vault / "constitutional").mkdir()
        gate = load_pre_action_gate(vault)
        assert gate.leeway_rules == []
        assert gate.constitutional_rules == []

    def test_empty_vault_gate_forbids_everything(self) -> None:
        vault = Path(tempfile.mkdtemp())
        (vault / "leeway").mkdir()
        (vault / "constitutional").mkdir()
        gate = load_pre_action_gate(vault)
        decision = gate.evaluate(_action("retrieve_from_memory"))
        assert decision.final_decision == "forbidden"

    def test_rule_ids_match_defaults(self) -> None:
        vault = _vault_with_defaults()
        gate = load_pre_action_gate(vault)
        loaded_ids = {r.rule_id for r in gate.leeway_rules}
        default_ids = {r.rule_id for r in DEFAULT_LEEWAY_RULES}
        assert loaded_ids == default_ids
