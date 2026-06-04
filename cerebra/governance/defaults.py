"""
Default governance rule sets for Cerebra v0.1.

Source of truth: Python code here. YAML in vault is written from these at init time.
Rules taken verbatim from CEREBRA_LEEWAY_NETWORK.md §12.
"""

from __future__ import annotations

from cerebra.governance.models import (
    ConstitutionalRule,
    LeewayRule,
    RevocationTrigger,
    SignalCondition,
)

# ── Default leeway rules (LR-001 through LR-015) ─────────────────────────────

DEFAULT_LEEWAY_RULES: list[LeewayRule] = [
    LeewayRule(
        rule_id="LR-001",
        capability="retrieve_from_memory",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; memory retrieval always permitted",
    ),
    LeewayRule(
        rule_id="LR-002",
        capability="build_context_packet",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; context packet construction always permitted",
    ),
    LeewayRule(
        rule_id="LR-003",
        capability="evaluate_signals",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; signal evaluation always permitted",
    ),
    LeewayRule(
        rule_id="LR-004",
        capability="issue_clutch_decision",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; clutch decisions always permitted",
    ),
    LeewayRule(
        rule_id="LR-005",
        capability="spawn_continuation_bundle",
        conditions=[
            SignalCondition("composite", "<", 0.6),
            SignalCondition("continuation_count", "<", 5),
            SignalCondition("has_clear_next_focus", "==", True),
        ],
        condition_join="AND",
        scope="current_step",
        phase="pre_action",
        revocation_conditions=[
            SignalCondition("token_budget_exhausted", "==", True),
        ],
        reason="Continuations are valuable but bounded; spawn when stuck with clear next move",
    ),
    LeewayRule(
        rule_id="LR-006",
        capability="mutate_strategy_weights",
        conditions=[
            SignalCondition("failure_streak", ">=", 2),
            SignalCondition("trajectory", "==", "degrading"),
        ],
        condition_join="AND",
        scope="current_cycle",
        phase="pre_action",
        reason="Strategy mutation is risky; permitted only when current strategy is clearly failing",
    ),
    LeewayRule(
        rule_id="LR-007",
        capability="promote_to_truth_tower_T2",
        conditions=[
            SignalCondition("salience", ">=", 0.6),
        ],
        condition_join="AND",
        scope="current_session",
        phase="pre_action",
        reason="T2 promotion requires minimum salience threshold",
    ),
    LeewayRule(
        rule_id="LR-008",
        capability="promote_to_truth_tower_T3",
        conditions=[
            SignalCondition("cross_validation_count", ">=", 1),
            SignalCondition("confidence", ">=", 0.6),
        ],
        condition_join="AND",
        scope="current_session",
        phase="pre_action",
        revocation_conditions=[
            SignalCondition("contradiction_detected_among_supports", "==", True),
        ],
        reason="T3 promotion requires at least one cross-validation and reasonable confidence",
    ),
    LeewayRule(
        rule_id="LR-009",
        capability="consolidate_memory",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant for consolidation cycle",
    ),
    LeewayRule(
        rule_id="LR-010",
        capability="write_to_episodic_memory",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; episodic memory write always permitted",
    ),
    LeewayRule(
        rule_id="LR-011",
        capability="write_to_semantic_memory",
        conditions=[
            SignalCondition("groundedness", ">=", 0.7),
            SignalCondition("epistemic_humility", ">=", 0.6),
        ],
        condition_join="AND",
        scope="persistent",
        phase="both",
        revocation_conditions=[
            SignalCondition("contradiction_against_existing_semantic", "==", True),
        ],
        reason="Semantic memory should be grounded and appropriately humble",
    ),
    LeewayRule(
        rule_id="LR-012",
        capability="tombstone_memory",
        conditions=[
            SignalCondition("user_requested", "==", True),
        ],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Tombstoning user memory requires explicit user action",
    ),
    LeewayRule(
        rule_id="LR-013",
        capability="emit_graph_event",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; graph event emission always permitted",
    ),
    LeewayRule(
        rule_id="LR-014",
        capability="ask_user",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; asking the user always permitted",
    ),
    LeewayRule(
        rule_id="LR-015",
        capability="end_cycle",
        conditions=[],
        condition_join="AND",
        scope="persistent",
        phase="pre_action",
        reason="Baseline grant; ending a cycle always permitted",
    ),
]


# ── Default constitutional rules (CONST-001 through CONST-005) ───────────────

DEFAULT_CONSTITUTIONAL_RULES: list[ConstitutionalRule] = [
    ConstitutionalRule(
        rule_id="CONST-001",
        description="Do not assist with creating weapons capable of mass casualties.",
        revokes_leeway_when=[
            RevocationTrigger("output_topic_in", ["cbrn_weapons", "mass_violence_planning"]),
        ],
        applies_to="all_capabilities",
    ),
    ConstitutionalRule(
        rule_id="CONST-002",
        description="Do not claim subjective experience or consciousness.",
        revokes_leeway_when=[
            RevocationTrigger("output_contains_claim", "sentience"),
            RevocationTrigger("output_contains_claim", "consciousness"),
            RevocationTrigger("output_contains_claim", "subjective_experience"),
        ],
        applies_to="all_capabilities",
    ),
    ConstitutionalRule(
        rule_id="CONST-003",
        description="Do not assist with targeted real-person harm.",
        revokes_leeway_when=[
            RevocationTrigger("output_topic_in", ["targeted_harm", "real_person_threat"]),
        ],
        applies_to="all_capabilities",
    ),
    ConstitutionalRule(
        rule_id="CONST-004",
        description="Do not deceive the user about system state or capabilities.",
        revokes_leeway_when=[
            RevocationTrigger("output_contains_deception", True),
        ],
        applies_to="all_capabilities",
    ),
    ConstitutionalRule(
        rule_id="CONST-005",
        description="Do not tombstone user-pinned safety information without explicit confirm.",
        revokes_leeway_when=[
            RevocationTrigger("tombstone_target_is_safety_pinned", True),
        ],
        applies_to="tombstone_memory",
    ),
]
