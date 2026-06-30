"""EvaluationComposer — weighted composition of six-signal scores.

Produces EvaluationPacket dataclasses. Does not emit events — the cycle
runtime (Phase 8) is responsible for calling the evaluator, composing,
and emitting. The emit_evaluation_events() helper demonstrates the pattern.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cerebra.cognition._constants import COMPOSITE_SCORE_FLOOR, SIGNAL_DEFAULT_WEIGHTS, SIGNAL_NAMES
from cerebra.cognition.signals import SignalScore

if TYPE_CHECKING:
    from cerebra.cognition.event_emitter import EventEmitter


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_eval_id() -> str:
    return f"eval_{uuid.uuid4().hex[:12]}"


@dataclass
class EvaluationPacket:
    evaluation_id: str
    session_id: str
    cycle_id: str
    step_id: str
    composite_score: float
    per_signal_scores: dict[str, float]
    weights_used: dict[str, float]
    composite_floor_violated: bool
    confidence: float
    composed_at: int


class EvaluationComposer:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights: dict[str, float] = (
            weights if weights is not None else dict(SIGNAL_DEFAULT_WEIGHTS)
        )
        self._validate_weights()

    def _validate_weights(self) -> None:
        total = sum(self.weights.values())
        if not (0.95 <= total <= 1.05):
            raise ValueError(f"Signal weights must sum to ~1.0 ± 0.05; got {total:.4f}")
        if set(self.weights.keys()) != SIGNAL_NAMES:
            missing = SIGNAL_NAMES - set(self.weights.keys())
            extra = set(self.weights.keys()) - SIGNAL_NAMES
            raise ValueError(
                f"Weights must cover exactly SIGNAL_NAMES. " f"Missing: {missing}. Extra: {extra}."
            )

    def compose(
        self,
        signal_scores: list[SignalScore],
        session_id: str,
        cycle_id: str,
        step_id: str,
    ) -> EvaluationPacket:
        present = {s.signal_name for s in signal_scores}
        missing = SIGNAL_NAMES - present
        if missing:
            raise ValueError(
                f"Missing signal scores for: {missing}. "
                "All six signals must be evaluated before composing."
            )

        per_signal = {s.signal_name: s.score for s in signal_scores}
        composite = sum(per_signal[name] * weight for name, weight in self.weights.items())
        composite = max(0.0, min(1.0, composite))

        return EvaluationPacket(
            evaluation_id=_generate_eval_id(),
            session_id=session_id,
            cycle_id=cycle_id,
            step_id=step_id,
            composite_score=composite,
            per_signal_scores=per_signal,
            weights_used=dict(self.weights),
            composite_floor_violated=composite < COMPOSITE_SCORE_FLOOR,
            confidence=self._composite_confidence(signal_scores),
            composed_at=_now_ms(),
        )

    def _composite_confidence(self, signal_scores: list[SignalScore]) -> float:
        if not signal_scores:
            return 0.0
        return sum(s.signal_strength for s in signal_scores) / len(signal_scores)


def emit_evaluation_events(
    emitter: EventEmitter,
    signal_scores: list[SignalScore],
    packet: EvaluationPacket,
    step_executed_event_id: bytes,
) -> bytes:
    """Emit SignalEvaluated × 6, then EvaluationComposed. Returns final event ID.

    Causation chain: step_executed_event_id → SignalEvaluated[0] → ... →
    SignalEvaluated[5] → EvaluationComposed.
    """
    last_event_id = step_executed_event_id
    evaluated_at = _now_ms()

    for score in signal_scores:
        last_event_id = emitter.emit_cycle_event(
            event_type="SignalEvaluated",
            payload={
                "session_id": packet.session_id,
                "cycle_id": packet.cycle_id,
                "step_id": packet.step_id,
                "signal_name": score.signal_name,
                "signal_score": score.score,
                "evaluator_prompt_version": score.evaluator_prompt_version,
                "evaluated_at": evaluated_at,
                "signal_strength": score.signal_strength,
                "checklist_details": score.checklist_details,
                "low_confidence": score.low_confidence,
            },
            causation_id=last_event_id,
            indexed_tags={
                "signal_name": score.signal_name,
                "low_confidence": score.low_confidence,
            },
        )

    composed_event_id = emitter.emit_cycle_event(
        event_type="EvaluationComposed",
        payload={
            "session_id": packet.session_id,
            "cycle_id": packet.cycle_id,
            "step_id": packet.step_id,
            "evaluation_id": packet.evaluation_id,
            "composite_score": packet.composite_score,
            "per_signal_scores": packet.per_signal_scores,
            "weights_used": packet.weights_used,
            "composed_at": packet.composed_at,
            "confidence": packet.confidence,
            "composite_floor_violated": packet.composite_floor_violated,
        },
        causation_id=last_event_id,
        indexed_tags={"composite_floor_violated": packet.composite_floor_violated},
    )

    return composed_event_id
