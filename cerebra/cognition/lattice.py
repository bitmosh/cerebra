# SPDX-License-Identifier: Apache-2.0
"""
Interpretive lattice — confidence-gated multi-commit decision logic.

Pure decision functions with no DB or event dependencies.
All writes and event emission live in SKUClassifier.classify_record_lattice().
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cerebra.cognition._constants import LATTICE_COMMIT_THRESHOLD
from cerebra.sources.hashing import hash_string


@dataclass
class LatticeDecision:
    """
    Result of evaluate_lattice().

    candidates: list of (category_name, confidence) pairs that cleared the
    threshold, sorted descending by confidence. Empty means no commit.
    threshold_used: the threshold that produced this decision.
    """

    candidates: list[tuple[str, float]]
    threshold_used: float

    @property
    def should_multi_commit(self) -> bool:
        return len(self.candidates) >= 2

    @property
    def top_1_category(self) -> str:
        return self.candidates[0][0]

    @property
    def top_1_confidence(self) -> float:
        return self.candidates[0][1]


def evaluate_lattice(
    scores: dict[str, float],
    threshold: float = LATTICE_COMMIT_THRESHOLD,
) -> LatticeDecision:
    """
    Evaluate the full score distribution and return a LatticeDecision.

    Any category scoring >= threshold becomes a candidate.
    If zero candidates: the chunk doesn't clear the threshold at all.
    If one candidate: normal single-commit.
    If two or more: multi-commit path.
    """
    candidates = sorted(
        [(k, v) for k, v in scores.items() if v >= threshold],
        key=lambda x: x[1],
        reverse=True,
    )
    return LatticeDecision(candidates=candidates, threshold_used=threshold)


def new_lineage_id() -> str:
    """Generate a fresh sibling lineage ID."""
    return f"lat_{uuid.uuid4().hex[:12]}"


def build_sibling_record_id(primary_record_id: str, category: str) -> str:
    """
    Deterministic record_id for a lattice sibling.

    Uses the same prefix convention as normal records ("rec_") but keyed on
    (primary_record_id, category) so the same chunk+category always maps to
    the same sibling id — enabling idempotent re-runs.
    """
    return "rec_" + hash_string(f"{primary_record_id}:{category}")[:12]
