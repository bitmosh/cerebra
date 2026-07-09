# SPDX-License-Identifier: Apache-2.0
"""Integration tests for SignalEvaluator against local Ollama.

These tests make real LLM calls — they are slow (up to 300s on cold model load)
and require Ollama running with the configured model.

Skip conditions:
  - CEREBRA_SKIP_OLLAMA=1 env var
  - Ollama unreachable (OllamaDirectAdapter().health_check() returns False)

Run only with: pytest -m integration (or pytest with default addopts)
Exclude with:  pytest -m "not integration"
"""

from __future__ import annotations

import os

import pytest

from cerebra.cognition._constants import SIGNAL_NAMES
from cerebra.cognition.llm_adapter import OllamaDirectAdapter
from cerebra.cognition.signals import SignalEvaluator

# ── skip logic ────────────────────────────────────────────────────────────────


def _ollama_available() -> bool:
    if os.environ.get("CEREBRA_SKIP_OLLAMA"):
        return False
    try:
        return OllamaDirectAdapter().health_check()
    except Exception:
        return False


_SKIP_OLLAMA = pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama not reachable or CEREBRA_SKIP_OLLAMA=1 — skipping integration tests",
)

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def evaluator() -> SignalEvaluator:
    adapter = OllamaDirectAdapter()
    return SignalEvaluator(llm_adapter=adapter)


# ── per-signal smoke tests ────────────────────────────────────────────────────

_WELL_FORMED_OUTPUT = (
    "Photosynthesis converts light energy into chemical energy. "
    "Plants absorb CO2 and water, using sunlight to produce glucose and oxygen. "
    "The process occurs in chloroplasts. "
    "Evidence: Campbell Biology (2019), ch. 10. "
    "I believe this summary is accurate, though details may vary by species."
)


@pytest.mark.integration
@_SKIP_OLLAMA
class TestPerSignalOllamaSmoke:
    def test_coherence_score_in_range(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("COHERENCE", _WELL_FORMED_OUTPUT)
        assert 0.0 <= score.score <= 1.0, f"COHERENCE score {score.score} out of range"

    def test_groundedness_score_in_range(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("GROUNDEDNESS", _WELL_FORMED_OUTPUT)
        assert 0.0 <= score.score <= 1.0

    def test_generativity_score_in_range(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("GENERATIVITY", _WELL_FORMED_OUTPUT)
        assert 0.0 <= score.score <= 1.0

    def test_relevance_score_in_range(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("RELEVANCE", _WELL_FORMED_OUTPUT)
        assert 0.0 <= score.score <= 1.0

    def test_precision_score_in_range(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("PRECISION", _WELL_FORMED_OUTPUT)
        assert 0.0 <= score.score <= 1.0

    def test_epistemic_humility_score_in_range(self, evaluator: SignalEvaluator) -> None:
        # Marker-based — no Ollama call needed, but test runs in integration suite
        score = evaluator.evaluate("EPISTEMIC_HUMILITY", _WELL_FORMED_OUTPUT)
        assert 0.0 <= score.score <= 1.0

    def test_evaluate_all_returns_six_scores(self, evaluator: SignalEvaluator) -> None:
        scores = evaluator.evaluate_all(_WELL_FORMED_OUTPUT)
        assert len(scores) == 6
        assert {s.signal_name for s in scores} == SIGNAL_NAMES


# ── semantic signal tests ─────────────────────────────────────────────────────

_CONTRADICTORY_OUTPUT = (
    "The Earth is round. The Earth is flat. "
    "Water freezes at 0°C. Water freezes at 100°C. "
    "Gravity pulls objects downward. Gravity pushes objects upward."
)

_GROUNDED_OUTPUT = (
    "According to NASA (2023), the Earth's average diameter is 12,742 km. "
    "Per NOAA data, global average temperature rose 1.1°C since 1900. "
    "The IPCC AR6 report (2021) attributes this primarily to greenhouse gas emissions. "
    "These sources are peer-reviewed and current as of 2023."
)


@pytest.mark.integration
@_SKIP_OLLAMA
class TestSemanticSignalBehavior:
    def test_coherence_low_for_contradictions(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("COHERENCE", _CONTRADICTORY_OUTPUT)
        assert (
            score.score < 0.5
        ), f"Contradictory output should score < 0.5 on COHERENCE; got {score.score:.3f}"

    def test_groundedness_high_for_cited_output(self, evaluator: SignalEvaluator) -> None:
        score = evaluator.evaluate("GROUNDEDNESS", _GROUNDED_OUTPUT)
        assert (
            score.score > 0.6
        ), f"Well-sourced output should score > 0.6 on GROUNDEDNESS; got {score.score:.3f}"
