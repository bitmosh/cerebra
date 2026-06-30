"""SignalEvaluator — six-signal epistemological evaluation of LLM outputs.

Evaluates one signal at a time. EPISTEMIC_HUMILITY uses marker-based scoring
(no LLM call). The other five signals use complete_structured() with Ollama
JSON mode for reliable score extraction.

DEV-005 note: each evaluation call produces a unique (event_type, payload,
causation_id) tuple at the EventEmitter layer — no CCE dedup risk.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from cerebra.cognition._constants import SIGNAL_NAMES
from cerebra.cognition.llm_adapter import ClassificationError, LLMAdapter
from cerebra.cognition.signal_prompts.epistemic_humility_v1 import (
    score_epistemic_humility,
)

# Stable iteration order for evaluate_all(). Must equal SIGNAL_NAMES.
SIGNAL_EVAL_ORDER: list[str] = [
    "COHERENCE",
    "GROUNDEDNESS",
    "GENERATIVITY",
    "RELEVANCE",
    "PRECISION",
    "EPISTEMIC_HUMILITY",
]

_SIGNAL_MODULE_MAP: dict[str, str] = {
    "COHERENCE": "cerebra.cognition.signal_prompts.coherence_v1",
    "GROUNDEDNESS": "cerebra.cognition.signal_prompts.groundedness_v1",
    "GENERATIVITY": "cerebra.cognition.signal_prompts.generativity_v1",
    "RELEVANCE": "cerebra.cognition.signal_prompts.relevance_v1",
    "PRECISION": "cerebra.cognition.signal_prompts.precision_v1",
    "EPISTEMIC_HUMILITY": "cerebra.cognition.signal_prompts.epistemic_humility_v1",
}


@dataclass
class SignalScore:
    signal_name: str
    score: float  # [0.0, 1.0], clamped
    evaluator_prompt_version: str
    signal_strength: float = 1.0  # v0.1 default; v0.2 adds strength scoring
    checklist_details: dict[str, Any] | None = None
    low_confidence: bool = False


class SignalEvaluator:
    def __init__(self, llm_adapter: LLMAdapter) -> None:
        self.llm_adapter = llm_adapter
        self._prompt_modules: dict[str, ModuleType] = self._load_prompt_modules()

    def _load_prompt_modules(self) -> dict[str, ModuleType]:
        modules: dict[str, ModuleType] = {}
        for signal_name, module_path in _SIGNAL_MODULE_MAP.items():
            modules[signal_name] = importlib.import_module(module_path)
        return modules

    def evaluate(
        self,
        signal_name: str,
        output_text: str,
        context: dict[str, Any] | None = None,
    ) -> SignalScore:
        if signal_name not in SIGNAL_NAMES:
            raise ValueError(f"Unknown signal: {signal_name!r}. Known signals: {SIGNAL_NAMES}")

        if signal_name == "EPISTEMIC_HUMILITY":
            score, details = score_epistemic_humility(output_text)
            return SignalScore(
                signal_name=signal_name,
                score=score,
                evaluator_prompt_version="epistemic_humility_v1",
                checklist_details=details,
            )

        prompt_module = self._prompt_modules[signal_name]
        prompt = prompt_module.render(output_text, context)

        try:
            response = self.llm_adapter.complete_structured(
                prompt,
                schema={"checks": "array", "overall_score": "number", "reasoning": "string"},
            )
        except ClassificationError:
            # LLM call failed — return low-confidence neutral score
            return SignalScore(
                signal_name=signal_name,
                score=0.5,
                evaluator_prompt_version=prompt_module.PROMPT_VERSION,
                low_confidence=True,
            )

        raw_score_val = response.get("overall_score", None)
        try:
            raw_float = float(raw_score_val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raw_float = 0.5
            clamped = True
        else:
            clamped = not (0.0 <= raw_float <= 1.0)

        score = max(0.0, min(1.0, raw_float))
        low_confidence = self._detect_low_confidence(response) or clamped

        return SignalScore(
            signal_name=signal_name,
            score=score,
            evaluator_prompt_version=prompt_module.PROMPT_VERSION,
            checklist_details=response,
            low_confidence=low_confidence,
        )

    def evaluate_all(
        self,
        output_text: str,
        context: dict[str, Any] | None = None,
    ) -> list[SignalScore]:
        """Evaluate all six signals. Returns list in SIGNAL_EVAL_ORDER."""
        return [self.evaluate(name, output_text, context) for name in SIGNAL_EVAL_ORDER]

    def _detect_low_confidence(self, response: dict[str, Any]) -> bool:
        """Flag structural response issues that suggest unreliable scoring."""
        if not response.get("checks"):
            return True
        if not response.get("reasoning"):
            return True
        return False
