"""
Cerebra compile-time constants.

Phase 5: working memory and truth tower capacities.
Phase 6: signal pipeline, prediction error thresholds, cycle runtime, clutch/catalyst.
Per-cycle overrides for Phase 8+ runtime are deferred to the cycle config layer.
"""

from __future__ import annotations

import os

SLOT_CAPACITIES: dict[str, int] = {
    "goal":          1,
    "constraint":    4,
    "context":       7,
    "hypothesis":    3,
    "evidence":      5,
    "contradiction": 2,
    "recent_output": 2,
    "question":      3,
    "procedure":     4,
    "interrupt":     3,
}

SLOT_CAPACITY_TOTAL: int = sum(SLOT_CAPACITIES.values())  # 34

TOWER_CAPACITIES: dict[int, int] = {
    1: 10,  # T1 source-grounded evidence
    2: 5,   # T2 high-salience memories
}

SYNTHETIC_ITEM_DEFAULT_SALIENCE: float = 0.8

# ── Interpretive lattice ──────────────────────────────────────────────────────
# Categories scoring at or above this threshold are committed as sibling records.
# Override with CEREBRA_LATTICE_THRESHOLD env var (e.g. "0.70" for tighter gating).
LATTICE_COMMIT_THRESHOLD: float = float(
    os.environ.get("CEREBRA_LATTICE_THRESHOLD", "0.65")
)

# ── Phase 6 — Signal pipeline ─────────────────────────────────────────────────

SIGNAL_NAMES: frozenset[str] = frozenset(
    {
        "COHERENCE",
        "GROUNDEDNESS",
        "GENERATIVITY",
        "RELEVANCE",
        "PRECISION",
        "EPISTEMIC_HUMILITY",
    }
)

SIGNAL_DEFAULT_WEIGHTS: dict[str, float] = {
    "COHERENCE": 0.18,
    "GROUNDEDNESS": 0.18,
    "GENERATIVITY": 0.12,
    "RELEVANCE": 0.22,
    "PRECISION": 0.12,
    "EPISTEMIC_HUMILITY": 0.18,
}

# Validate at module load: sum must be within 0.95–1.05 to catch real errors
# while tolerating floating-point representation drift.
_weight_sum = sum(SIGNAL_DEFAULT_WEIGHTS.values())
if not (0.95 <= _weight_sum <= 1.05):
    raise ValueError(
        f"SIGNAL_DEFAULT_WEIGHTS must sum to 1.0 ± 0.05; got {_weight_sum}"
    )

# Composite score below this floor triggers a refine action in the Clutch.
COMPOSITE_SCORE_FLOOR: float = 0.30

# Prediction error classification thresholds (absolute |error|).
# noise:    |error| < 0.10  — within expected variance, no action
# notable:  0.10 <= |error| < 0.40  — worth tracking, may inform calibration
# severe:   |error| >= 0.40  — emits PredictionSevereMiss, influences Clutch
PREDICTION_ERROR_CLASSIFIERS: dict[str, float] = {
    "noise": 0.10,
    "notable": 0.40,
    "severe": float("inf"),
}

# ── Phase 8 — Cycle runtime ───────────────────────────────────────────────────

# Hard cap on steps per cycle; per-cycle configs may set a lower limit.
CYCLE_MAX_STEPS: int = 20

# Maximum continuation chains per session (re-injection depth cap).
RECURSION_DEPTH_DEFAULT: int = 5

# ── Phase 9 — Clutch + Catalyst ───────────────────────────────────────────────

CLUTCH_ACTIONS: frozenset[str] = frozenset(
    {
        "accept",
        "refine",
        "critique",
        "explore",
        "branch",
        "retrieve_more",
        "consolidate",
        "ask_user",
        "pause",
        "stop",
    }
)

# ── Phase 8 — Stop condition types ───────────────────────────────────────────
STOP_CONDITION_TYPES: frozenset[str] = frozenset(
    {
        "max_steps_reached",
        "all_steps_completed",
        "composite_floor_consecutive",
        "explicit_clutch_stop",
        "user_interrupt",
    }
)

# ── Phase 8 — Built-in clutch predicate names (for CycleConfig validation) ───
BUILTIN_PREDICATE_NAMES: frozenset[str] = frozenset(
    {
        "at_terminal_step",
        "composite_below_threshold",
        "composite_above_threshold",
        "first_step",
        "step_index_at",
        "always",
    }
)

# ── Phase 6+ — Event types ────────────────────────────────────────────────────
# Mirrors PHASE_6_EVENT_TYPES in cerebra/inspector/event.py.
# Defined here for use in cognition-layer code that must not import from inspector.

PHASE_6_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # Session + cycle lifecycle
        "SessionOpened",
        "CycleStarted",
        "CycleCompleted",
        # Step execution
        "StepStarted",
        "ContextPacketBuilt",
        "StepExecuted",
        "StepExecutionFailed",
        # Prediction + evaluation
        "PredictionMade",
        "SignalEvaluated",
        "EvaluationComposed",
        "OutcomeRecorded",
        "PredictionSevereMiss",
        # Control decisions
        "ClutchDecisionMade",
        "CatalystInvoked",
        "CatalystArmSelected",
        # Safety gate
        "LeewayGrantApplied",
        # Re-injection
        "ContinuationBundleCreated",
        "ReinjectionTriggered",
        # Working memory + session end
        "MemoryWriteFromCycle",
        "SessionFlushed",
        # Consolidation (Phase 10)
        "ConsolidationStarted",
        "ConsolidationCompleted",
        # Graph export (Phase 11)
        "GraphExported",
    }
)

# ── Phase 6+ — Lattice snapshot discipline ───────────────────────────────────

# Lattice node streams snapshot every N events at cycle boundaries.
# Keeps replay windows small; see design doc §3.2 for snapshot trigger mechanics.
LATTICE_SNAPSHOT_CADENCE: int = 100
