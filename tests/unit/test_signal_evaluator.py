"""Unit tests for SignalEvaluator with a mock LLM adapter.

Tests cover signal-by-signal evaluation, EPISTEMIC_HUMILITY marker path,
score clamping, evaluate_all() ordering, and error handling.
"""

from __future__ import annotations

import pytest

from cerebra.cognition._constants import SIGNAL_NAMES
from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult
from cerebra.cognition.signals import SIGNAL_EVAL_ORDER, SignalEvaluator, SignalScore

# ── mock adapter ──────────────────────────────────────────────────────────────


class _MockStructuredResponse:
    """Returns a configurable JSON dict from complete_structured()."""

    def __init__(self, score: float = 0.75, reasoning: str = "test reason") -> None:
        self._score = score
        self._reasoning = reasoning

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return "mock text response"

    def complete_structured(self, prompt: str, schema: dict) -> dict:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": self._score,
            "reasoning": self._reasoning,
        }

    def classify_d1(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


class _MockFailingAdapter(_MockStructuredResponse):
    """Raises ClassificationError from complete_structured."""

    def complete_structured(self, prompt: str, schema: dict) -> dict:
        raise ClassificationError("mock LLM failure")


class _MockBadScoreAdapter(_MockStructuredResponse):
    """Returns score outside [0, 1]."""

    def complete_structured(self, prompt: str, schema: dict) -> dict:
        return {
            "checks": [{"item": 1, "severity": 0, "specific_lines": ""}],
            "overall_score": 1.8,
            "reasoning": "bad score",
        }


class _MockMissingScoreAdapter(_MockStructuredResponse):
    """Returns response without overall_score."""

    def complete_structured(self, prompt: str, schema: dict) -> dict:
        return {"checks": [], "reasoning": ""}


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_evaluator(score: float = 0.75) -> SignalEvaluator:
    return SignalEvaluator(llm_adapter=_MockStructuredResponse(score=score))  # type: ignore[arg-type]


_SAMPLE_OUTPUT = "The sky is blue. Rayleigh scattering explains this phenomenon."


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSignalEvaluatorBasic:
    def test_evaluate_each_signal_returns_signal_score(self) -> None:
        ev = _make_evaluator()
        for name in SIGNAL_NAMES:
            score = ev.evaluate(name, _SAMPLE_OUTPUT)
            assert isinstance(score, SignalScore), f"{name}: not a SignalScore"

    def test_score_in_range_for_all_signals(self) -> None:
        ev = _make_evaluator()
        for name in SIGNAL_NAMES:
            score = ev.evaluate(name, _SAMPLE_OUTPUT)
            assert 0.0 <= score.score <= 1.0, f"{name}: score {score.score} out of [0,1]"

    def test_signal_name_preserved(self) -> None:
        ev = _make_evaluator()
        for name in SIGNAL_NAMES:
            score = ev.evaluate(name, _SAMPLE_OUTPUT)
            assert score.signal_name == name

    def test_unknown_signal_raises(self) -> None:
        ev = _make_evaluator()
        with pytest.raises(ValueError, match="Unknown signal"):
            ev.evaluate("MADE_UP_SIGNAL", _SAMPLE_OUTPUT)

    def test_prompt_version_set(self) -> None:
        ev = _make_evaluator()
        for name in SIGNAL_NAMES:
            score = ev.evaluate(name, _SAMPLE_OUTPUT)
            assert score.evaluator_prompt_version, f"{name}: empty prompt_version"


@pytest.mark.unit
class TestEpistemicHumilityPath:
    def test_epistemic_humility_uses_marker_path(self) -> None:
        # Adapter that fails on complete_structured — humility should still work
        ev = SignalEvaluator(llm_adapter=_MockFailingAdapter())  # type: ignore[arg-type]
        score = ev.evaluate("EPISTEMIC_HUMILITY", _SAMPLE_OUTPUT)
        assert isinstance(score, SignalScore)
        assert 0.0 <= score.score <= 1.0

    def test_epistemic_humility_empty_output_scores_neutral(self) -> None:
        ev = _make_evaluator()
        score = ev.evaluate("EPISTEMIC_HUMILITY", "")
        assert score.score == pytest.approx(0.5)

    def test_uncertainty_markers_boost_score(self) -> None:
        ev = _make_evaluator()
        hedged = "I think this is probably true, though I'm not sure and it might be wrong."
        confident = "This is definitely true and certainly correct."
        hedged_score = ev.evaluate("EPISTEMIC_HUMILITY", hedged)
        confident_score = ev.evaluate("EPISTEMIC_HUMILITY", confident)
        assert hedged_score.score > confident_score.score, (
            f"Hedged ({hedged_score.score:.3f}) should score higher than "
            f"confident ({confident_score.score:.3f})"
        )

    def test_overclaiming_lowers_score(self) -> None:
        ev = _make_evaluator()
        overclaiming = (
            "Definitely this is certainly absolutely the truth. Always and without doubt."
        )
        baseline = "The sky appears blue during daytime."
        overclaim_score = ev.evaluate("EPISTEMIC_HUMILITY", overclaiming)
        baseline_score = ev.evaluate("EPISTEMIC_HUMILITY", baseline)
        assert overclaim_score.score < baseline_score.score, (
            f"Overclaiming ({overclaim_score.score:.3f}) should score lower than "
            f"baseline ({baseline_score.score:.3f})"
        )

    def test_epistemic_humility_prompt_version(self) -> None:
        ev = _make_evaluator()
        score = ev.evaluate("EPISTEMIC_HUMILITY", _SAMPLE_OUTPUT)
        assert score.evaluator_prompt_version == "epistemic_humility_v1"

    def test_epistemic_humility_has_checklist_details(self) -> None:
        ev = _make_evaluator()
        score = ev.evaluate("EPISTEMIC_HUMILITY", _SAMPLE_OUTPUT)
        assert score.checklist_details is not None
        assert "marker_count" in score.checklist_details


@pytest.mark.unit
class TestEvaluateAll:
    def test_evaluate_all_returns_six_scores(self) -> None:
        ev = _make_evaluator()
        scores = ev.evaluate_all(_SAMPLE_OUTPUT)
        assert len(scores) == 6

    def test_evaluate_all_stable_order(self) -> None:
        ev = _make_evaluator()
        scores = ev.evaluate_all(_SAMPLE_OUTPUT)
        names = [s.signal_name for s in scores]
        assert names == SIGNAL_EVAL_ORDER

    def test_evaluate_all_covers_all_signals(self) -> None:
        ev = _make_evaluator()
        scores = ev.evaluate_all(_SAMPLE_OUTPUT)
        assert {s.signal_name for s in scores} == SIGNAL_NAMES

    def test_evaluate_all_with_context(self) -> None:
        ev = _make_evaluator()
        scores = ev.evaluate_all(_SAMPLE_OUTPUT, context={"goal": "explain physics"})
        assert len(scores) == 6


@pytest.mark.unit
class TestScoreClamping:
    def test_score_above_1_is_clamped(self) -> None:
        ev = SignalEvaluator(llm_adapter=_MockBadScoreAdapter())  # type: ignore[arg-type]
        score = ev.evaluate("COHERENCE", _SAMPLE_OUTPUT)
        assert score.score == pytest.approx(1.0)
        assert score.low_confidence is True

    def test_llm_failure_returns_neutral_low_confidence(self) -> None:
        ev = SignalEvaluator(llm_adapter=_MockFailingAdapter())  # type: ignore[arg-type]
        score = ev.evaluate("COHERENCE", _SAMPLE_OUTPUT)
        assert score.score == pytest.approx(0.5)
        assert score.low_confidence is True

    def test_missing_score_in_response_returns_low_confidence(self) -> None:
        ev = SignalEvaluator(llm_adapter=_MockMissingScoreAdapter())  # type: ignore[arg-type]
        score = ev.evaluate("COHERENCE", _SAMPLE_OUTPUT)
        assert score.low_confidence is True
