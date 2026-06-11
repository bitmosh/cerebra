"""
Phase 5 working memory and truth tower capacity constants.

These are compile-time constants in Phase 5. Per-cycle overrides are deferred
to Phase 8+ when the cycle runtime is built.
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
