"""Tests for signal prompt modules.

Verifies each module loads, exports PROMPT_VERSION (unique across all modules),
and that render() produces a non-empty string with output substituted in.
"""

from __future__ import annotations

import pytest

from cerebra.cognition.signal_prompts import (
    coherence_v1,
    epistemic_humility_v1,
    generativity_v1,
    groundedness_v1,
    precision_v1,
    relevance_v1,
)


@pytest.mark.unit
class TestPromptModuleAttributes:
    def test_all_modules_have_prompt_version(self) -> None:
        for mod in (coherence_v1, groundedness_v1, generativity_v1,
                    relevance_v1, precision_v1, epistemic_humility_v1):
            assert hasattr(mod, "PROMPT_VERSION"), f"{mod.__name__} missing PROMPT_VERSION"
            assert isinstance(mod.PROMPT_VERSION, str)
            assert mod.PROMPT_VERSION.strip()

    def test_prompt_versions_are_unique(self) -> None:
        versions = [
            coherence_v1.PROMPT_VERSION,
            groundedness_v1.PROMPT_VERSION,
            generativity_v1.PROMPT_VERSION,
            relevance_v1.PROMPT_VERSION,
            precision_v1.PROMPT_VERSION,
            epistemic_humility_v1.PROMPT_VERSION,
        ]
        assert len(versions) == len(set(versions)), f"Duplicate PROMPT_VERSIONs: {versions}"

    def test_all_modules_have_render(self) -> None:
        for mod in (coherence_v1, groundedness_v1, generativity_v1,
                    relevance_v1, precision_v1, epistemic_humility_v1):
            assert callable(getattr(mod, "render", None)), f"{mod.__name__} missing render()"


@pytest.mark.unit
class TestRenderSubstitution:
    _SAMPLE_OUTPUT = "The sky is blue because of Rayleigh scattering."

    def _check_render(self, mod, output: str = _SAMPLE_OUTPUT) -> str:
        result = mod.render(output)
        assert isinstance(result, str)
        assert result.strip(), f"{mod.__name__}.render() returned empty string"
        assert output in result, f"{mod.__name__}.render() did not embed output text"
        return result

    def test_coherence_render(self) -> None:
        self._check_render(coherence_v1)

    def test_groundedness_render(self) -> None:
        self._check_render(groundedness_v1)

    def test_generativity_render(self) -> None:
        self._check_render(generativity_v1)

    def test_relevance_render(self) -> None:
        self._check_render(relevance_v1)

    def test_precision_render(self) -> None:
        self._check_render(precision_v1)

    def test_epistemic_humility_render(self) -> None:
        # epistemic_humility_v1.render() is a stub in v0.1 — just check it runs
        result = epistemic_humility_v1.render(self._SAMPLE_OUTPUT)
        assert isinstance(result, str)

    def test_render_with_context(self) -> None:
        ctx = {"goal": "explain physics"}
        result = coherence_v1.render(self._SAMPLE_OUTPUT, context=ctx)
        assert self._SAMPLE_OUTPUT in result

    def test_render_with_none_context(self) -> None:
        result = coherence_v1.render(self._SAMPLE_OUTPUT, context=None)
        assert self._SAMPLE_OUTPUT in result

    def test_version_string_format(self) -> None:
        assert coherence_v1.PROMPT_VERSION == "coherence_v1"
        assert groundedness_v1.PROMPT_VERSION == "groundedness_v1"
        assert generativity_v1.PROMPT_VERSION == "generativity_v1"
        assert relevance_v1.PROMPT_VERSION == "relevance_v1"
        assert precision_v1.PROMPT_VERSION == "precision_v1"
        assert epistemic_humility_v1.PROMPT_VERSION == "epistemic_humility_v1"


@pytest.mark.unit
class TestEpistemicHumilityMarkers:
    def test_uncertainty_markers_is_frozenset(self) -> None:
        assert isinstance(epistemic_humility_v1.UNCERTAINTY_MARKERS, frozenset)

    def test_overclaiming_patterns_is_frozenset(self) -> None:
        assert isinstance(epistemic_humility_v1.OVERCLAIMING_PATTERNS, frozenset)

    def test_markers_not_empty(self) -> None:
        assert len(epistemic_humility_v1.UNCERTAINTY_MARKERS) > 0
        assert len(epistemic_humility_v1.OVERCLAIMING_PATTERNS) > 0
