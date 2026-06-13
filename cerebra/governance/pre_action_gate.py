"""Phase 7 — Leeway pre-action gate."""

from __future__ import annotations

from cerebra.governance.models import ConstitutionalRule, LeewayRule
from cerebra.governance.types import GateDecision, ProposedAction


class LeewayPreActionGate:
    """Evaluates proposed actions against loaded leeway and constitutional rules.

    Composition-by-union semantics: ANY leeway rule granting permission is
    sufficient for "permitted", unless a constitutional rule forbids (DEV-009:
    constitutional forbids always return False in v0.1).

    requires_review decision deferred to v0.2 (DEV-010): no HITL consumer exists.
    """

    def __init__(
        self,
        leeway_rules: list[LeewayRule],
        constitutional_rules: list[ConstitutionalRule],
    ) -> None:
        self.leeway_rules = leeway_rules
        self.constitutional_rules = constitutional_rules

    def evaluate(self, proposed_action: ProposedAction) -> GateDecision:
        """Evaluate a proposed action and return a two-state decision (v0.1).

        Evaluation order:
          1. Constitutional forbids — highest priority (all return False in v0.1).
          2. Leeway grants — composition-by-union, matching capability + phase.
          3. No grants → forbidden with forbidden_by="no_grants".
          4. Grants present → permitted.
        """
        # 1. Constitutional forbids (no-op in v0.1; called for forward compat — DEV-009)
        for c_rule in self.constitutional_rules:
            if c_rule.forbids(proposed_action):
                return GateDecision(
                    final_decision="forbidden",
                    proposed_action=proposed_action,
                    grants_applied=[],
                    forbidden_by=c_rule.rule_id,
                )

        # 2. Collect grants (composition-by-union)
        grants = [r.rule_id for r in self.leeway_rules if r.grants(proposed_action)]
        if not grants:
            return GateDecision(
                final_decision="forbidden",
                proposed_action=proposed_action,
                grants_applied=[],
                forbidden_by="no_grants",
            )

        # 3. requires_review deferred to v0.2 (DEV-010)

        # 4. Permitted
        return GateDecision(
            final_decision="permitted",
            proposed_action=proposed_action,
            grants_applied=grants,
        )
