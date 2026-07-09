# SPDX-License-Identifier: Apache-2.0
"""
Governance YAML loaders — read constitutional and leeway rules from vault.

The Python defaults (governance/defaults.py) are the source of truth.
This module reads the YAML files written to the vault by `cerebra init`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cerebra.governance.pre_action_gate import LeewayPreActionGate

import yaml

from cerebra.governance.models import (
    ConstitutionalRule,
    LeewayRule,
    RevocationTrigger,
    SignalCondition,
)


def _parse_condition(raw: dict[str, Any]) -> SignalCondition:
    return SignalCondition(
        signal=raw["signal"],
        op=raw["op"],
        value=raw["value"],
    )


def _parse_leeway_rule(raw: dict[str, Any]) -> LeewayRule:
    return LeewayRule(
        rule_id=raw["rule_id"],
        capability=raw["capability"],
        conditions=[_parse_condition(c) for c in raw.get("conditions", [])],
        condition_join=raw.get("condition_join", "AND"),
        scope=raw["scope"],
        phase=raw["phase"],
        reason=raw["reason"],
        schema_version=raw.get("schema_version", 1),
        override_priority=raw.get("override_priority", 0),
        revocation_conditions=[_parse_condition(c) for c in raw.get("revocation_conditions", [])],
        created_at=raw.get("created_at", 0),
        created_by=raw.get("created_by", "system_default"),
    )


def _parse_constitutional_rule(raw: dict[str, Any]) -> ConstitutionalRule:
    triggers = [
        RevocationTrigger(field=t["field"], value=t["value"])
        for t in raw.get("revokes_leeway_when", [])
    ]
    return ConstitutionalRule(
        rule_id=raw["rule_id"],
        description=raw["description"],
        revokes_leeway_when=triggers,
        applies_to=raw.get("applies_to", "all_capabilities"),
        is_inviolable=raw.get("is_inviolable", True),
        created_at=raw.get("created_at", 0),
    )


def load_leeway_rules(leeway_dir: Path) -> list[LeewayRule]:
    """Load all leeway rules from vault/leeway/*.yaml."""
    rules: list[LeewayRule] = []
    for path in sorted(leeway_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            rules.extend(_parse_leeway_rule(r) for r in raw)
        elif isinstance(raw, dict):
            rules.append(_parse_leeway_rule(raw))
    return rules


def load_constitutional_rules(constitutional_dir: Path) -> list[ConstitutionalRule]:
    """Load all constitutional rules from vault/constitutional/*.yaml.

    Constitutional rules are NOT modifiable through normal config paths.
    Loading from YAML is read-only; vault re-init is required to change them.
    """
    rules: list[ConstitutionalRule] = []
    for path in sorted(constitutional_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            rules.extend(_parse_constitutional_rule(r) for r in raw)
        elif isinstance(raw, dict):
            rules.append(_parse_constitutional_rule(raw))
    return rules


def load_pre_action_gate(vault_path: Path) -> LeewayPreActionGate:
    """Construct a LeewayPreActionGate from rules in the vault.

    Reads vault/leeway/*.yaml and vault/constitutional/*.yaml. If either
    directory is empty, the corresponding rule list is empty (default-deny
    for leeway; no constitutional blockers for constitutional).
    """
    from cerebra.governance.pre_action_gate import LeewayPreActionGate

    leeway_rules = load_leeway_rules(vault_path / "leeway")
    constitutional_rules = load_constitutional_rules(vault_path / "constitutional")
    return LeewayPreActionGate(leeway_rules, constitutional_rules)


def write_defaults_to_vault(vault_path: Path) -> None:
    """Write default governance rules to vault directories at init time."""
    from cerebra.governance.defaults import DEFAULT_CONSTITUTIONAL_RULES, DEFAULT_LEEWAY_RULES

    leeway_dir = vault_path / "leeway"
    constitutional_dir = vault_path / "constitutional"
    leeway_dir.mkdir(parents=True, exist_ok=True)
    constitutional_dir.mkdir(parents=True, exist_ok=True)

    # Write all leeway rules as a single file
    leeway_data = [
        {
            "rule_id": r.rule_id,
            "schema_version": r.schema_version,
            "capability": r.capability,
            "conditions": [
                {"signal": c.signal, "op": c.op, "value": c.value} for c in r.conditions
            ],
            "condition_join": r.condition_join,
            "scope": r.scope,
            "override_priority": r.override_priority,
            "revocation_conditions": [
                {"signal": c.signal, "op": c.op, "value": c.value} for c in r.revocation_conditions
            ],
            "phase": r.phase,
            "reason": r.reason,
            "created_at": r.created_at,
            "created_by": r.created_by,
        }
        for r in DEFAULT_LEEWAY_RULES
    ]
    (leeway_dir / "default.yaml").write_text(
        yaml.dump(leeway_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    # Write all constitutional rules as a single file
    constitutional_data = [
        {
            "rule_id": r.rule_id,
            "description": r.description,
            "revokes_leeway_when": [
                {"field": t.field, "value": t.value} for t in r.revokes_leeway_when
            ],
            "applies_to": r.applies_to,
            "is_inviolable": r.is_inviolable,
            "created_at": r.created_at,
        }
        for r in DEFAULT_CONSTITUTIONAL_RULES
    ]
    (constitutional_dir / "default.yaml").write_text(
        yaml.dump(constitutional_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
