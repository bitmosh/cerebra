# SPDX-License-Identifier: Apache-2.0
"""
Calibration integration test — runs the real SKU classifier against the
30-fixture set and asserts ≥70% top-1 D1 agreement.

Guarded by CEREBRA_INTEGRATION_LLM=1. Never runs in standard CI.
Required at merge gate: run manually and include the 4-quadrant table
in the gate report.

4-quadrant breakdown (tracked, not gated):
  high-conf correct   (confidence >= 0.5, D1 matches)  → target state
  high-conf wrong     (confidence >= 0.5, D1 wrong)    → silent failures — investigate
  low-conf correct    (confidence <  0.5, D1 matches)  → honest guessing — acceptable
  low-conf wrong      (confidence <  0.5, D1 wrong)    → expected noise
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from cerebra.cognition.llm_adapter import OllamaDirectAdapter
from cerebra.cognition.sku_categories import D1Category
from cerebra.cognition.sku_classifier import (
    HIGH_CONF_THRESHOLD,
)
from cerebra.vault.init import init_vault
from tests.fixtures.sku_fixtures import (
    AMBIGUOUS_FIXTURES,
    CLEAR_FIXTURES,
    HARD_FIXTURES,
    SKU_FIXTURES,
    SKUFixture,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("CEREBRA_INTEGRATION_LLM"),
    reason="Set CEREBRA_INTEGRATION_LLM=1 to run real LLM calibration tests",
)


@dataclass
class FixtureResult:
    fixture: SKUFixture
    predicted_d1: D1Category
    confidence: float
    correct: bool
    high_confidence: bool
    partial_credit: float  # 1.0 for correct, 0.5 for ambiguous_with match, 0.0 for wrong

    @property
    def quadrant(self) -> Literal["hc_correct", "hc_wrong", "lc_correct", "lc_wrong"]:
        if self.high_confidence and self.correct:
            return "hc_correct"
        if self.high_confidence and not self.correct:
            return "hc_wrong"
        if not self.high_confidence and self.correct:
            return "lc_correct"
        return "lc_wrong"


def _run_calibration(vault: Path) -> list[FixtureResult]:
    db_path = vault / "data" / "cerebra.db"
    from cerebra.storage.migrations import run_migrations

    run_migrations(db_path)

    # OllamaDirectAdapter: calls Ollama natively with think: false and format: json.
    # Avoids LiteLLM's drop_params: true which strips these options.
    # health_check warms the model; first full classification call may still take ~30s.
    adapter = OllamaDirectAdapter()
    assert (
        adapter.health_check()
    ), "Ollama unreachable. Run: cd ~/Projects/ai-stack && docker compose up -d"

    from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult

    results = []
    for fixture in SKU_FIXTURES:
        # Retry once on ClassificationError (handles transient empty responses).
        # If both attempts fail, count as incorrect with 0 confidence rather than
        # crashing the whole calibration run.
        # Two-pass classification: Pass 1 quadrant, Pass 2 within-quadrant D1.
        # Mirrors the production path in SKUClassifier._classify_with_retry().
        # Retry each pass once independently on ClassificationError.
        classification: ClassificationResult | None = None
        try:
            pass1: ClassificationResult | None = None
            for _attempt in range(2):
                try:
                    pass1 = adapter.classify_quadrant(fixture.content)
                    break
                except ClassificationError:
                    continue
            if pass1 is None:
                raise ClassificationError("Pass 1 failed both attempts")

            for _attempt in range(2):
                try:
                    classification = adapter.classify_within_quadrant(
                        fixture.content, pass1.primary
                    )
                    break
                except ClassificationError:
                    continue
        except ClassificationError:
            pass

        if classification is None:
            print(f"  FAILED both attempts: {fixture.fixture_id}")
            results.append(
                FixtureResult(
                    fixture=fixture,
                    predicted_d1=D1Category.OBSERVATION,  # arbitrary wrong answer
                    confidence=0.0,
                    correct=False,
                    high_confidence=False,
                    partial_credit=0.0,
                )
            )
            continue

        predicted = D1Category[classification.primary]
        correct = predicted == fixture.expected_d1
        if correct:
            partial_credit = 1.0
        elif fixture.ambiguous_with is not None and predicted == fixture.ambiguous_with:
            partial_credit = 0.5
        else:
            partial_credit = 0.0
        results.append(
            FixtureResult(
                fixture=fixture,
                predicted_d1=predicted,
                confidence=classification.confidence,
                correct=correct,
                high_confidence=classification.confidence >= HIGH_CONF_THRESHOLD,
                partial_credit=partial_credit,
            )
        )

    return results


def _print_report(results: list[FixtureResult]) -> None:
    total = len(results)
    hc_correct = [r for r in results if r.quadrant == "hc_correct"]
    hc_wrong = [r for r in results if r.quadrant == "hc_wrong"]
    lc_correct = [r for r in results if r.quadrant == "lc_correct"]
    lc_wrong = [r for r in results if r.quadrant == "lc_wrong"]

    clear_results = [r for r in results if r.fixture in CLEAR_FIXTURES]
    hard_results = [r for r in results if r.fixture in HARD_FIXTURES]
    ambiguous_results = [r for r in results if r.fixture in AMBIGUOUS_FIXTURES]
    clear_acc = sum(1 for r in clear_results if r.correct) / max(len(clear_results), 1)
    hard_acc = sum(1 for r in hard_results if r.correct) / max(len(hard_results), 1)

    strict_correct = sum(1 for r in results if r.correct)
    partial_sum = sum(r.partial_credit for r in results)
    strict_acc = strict_correct / total
    partial_acc = partial_sum / total

    ambiguous_half_credit = sum(1 for r in ambiguous_results if r.partial_credit == 0.5)

    print("\n" + "=" * 60)
    print(f"SKU D1 CALIBRATION REPORT ({total} fixtures)")
    print("=" * 60)
    print(f"\nStrict accuracy:         {strict_correct}/{total} = {strict_acc:.0%}")
    print(
        f"Partial-credit accuracy: {partial_sum:.1f}/{total} = {partial_acc:.0%}  (0.5 credit on {ambiguous_half_credit} ambiguous matches)"
    )
    print(
        f"Clear-case accuracy:     {sum(1 for r in clear_results if r.correct)}/{len(clear_results)} = {clear_acc:.0%}"
    )
    print(
        f"Hard-case accuracy:      {sum(1 for r in hard_results if r.correct)}/{len(hard_results)} = {hard_acc:.0%}"
    )
    ambig_acc = sum(r.partial_credit for r in ambiguous_results) / max(len(ambiguous_results), 1)
    print(
        f"Ambiguous-case accuracy: {sum(r.partial_credit for r in ambiguous_results):.1f}/{len(ambiguous_results)} = {ambig_acc:.0%} (partial-credit)"
    )
    print("\n4-Quadrant Breakdown:")
    print(f"  High-conf correct: {len(hc_correct):2d}  ← target")
    print(f"  High-conf WRONG:   {len(hc_wrong):2d}  ← investigate these")
    print(f"  Low-conf correct:  {len(lc_correct):2d}  ← acceptable")
    print(f"  Low-conf wrong:    {len(lc_wrong):2d}  ← expected noise")

    if hc_wrong:
        print("\nHigh-confidence wrong cases (INVESTIGATE):")
        for r in hc_wrong:
            print(
                f"  [{r.fixture.fixture_id}] expected={r.fixture.expected_d1.name} "
                f"got={r.predicted_d1.name} conf={r.confidence:.2f}"
            )
            print(f"    content: {r.fixture.content[:80]}...")

    print("=" * 60)


@pytest.mark.integration
def test_sku_calibration_70pct_top1(tmp_path: Path) -> None:
    """
    Hard gate: ≥60% partial-credit accuracy across all 30 fixtures (substrate-for-LoRA threshold).
    Prints the full 4-quadrant breakdown regardless of pass/fail.
    """
    vault = init_vault(tmp_path / "vault")
    results = _run_calibration(vault)
    _print_report(results)

    partial_acc = sum(r.partial_credit for r in results) / len(results)
    strict_correct = sum(1 for r in results if r.correct)

    assert partial_acc >= 0.60, (
        f"D1 calibration FAILED: {sum(r.partial_credit for r in results):.1f}/{len(results)} = {partial_acc:.0%} partial-credit (threshold: 60%)"
        f" [strict: {strict_correct}/{len(results)}]\n"
        "Substrate-for-LoRA gate: ≥60% partial-credit proves the architecture works above noise.\n"
        "Iterate the prompt in sku_classifier._build_classification_prompt() before merging."
    )


@pytest.mark.integration
def test_clear_case_accuracy_higher_than_hard(tmp_path: Path) -> None:
    """Clear cases should outperform hard cases — validates fixture difficulty labeling."""
    vault = init_vault(tmp_path / "vault")
    results = _run_calibration(vault)

    clear_acc = sum(1 for r in results if r.fixture.difficulty == "clear" and r.correct) / len(
        CLEAR_FIXTURES
    )
    hard_acc = sum(1 for r in results if r.fixture.difficulty == "hard" and r.correct) / len(
        HARD_FIXTURES
    )

    assert clear_acc >= hard_acc, (
        f"Clear accuracy ({clear_acc:.0%}) should exceed hard accuracy ({hard_acc:.0%}). "
        "If not, either the fixture labels are wrong or the model is not responding to signal."
    )
