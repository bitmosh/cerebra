"""Prediction/outcome pipeline for the six-signal epistemology.

PredictionPipeline.predict() selects the most informed basis available
(prior step trajectory > cycle config defaults > static baseline) and
produces a PredictionRecord before each cognitive step executes.

PredictionPipeline.resolve() compares the actual EvaluationPacket to the
prediction, computes signed prediction error, classifies it (noise /
notable / severe), and returns an OutcomeRecord.

Both records persist to SQLite (write_prediction / write_outcome) alongside
fossic event emission. SQLite is the query surface; fossic is the audit
surface.

PredictionInput decouples this module from Phase 8's SessionState type.
Phase 8 will produce PredictionInput from real SessionState via a thin
adapter; the pipeline logic here stays unchanged.

NOTE: Confidence heuristics in _select_basis are v0.1 placeholders.
v0.2 will calibrate against ground truth outcomes.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cerebra.cognition._constants import PREDICTION_ERROR_CLASSIFIERS, SIGNAL_NAMES
from cerebra.storage.db import connect

if TYPE_CHECKING:
    from cerebra.cognition.evaluation import EvaluationComposer, EvaluationPacket
    from cerebra.cognition.event_emitter import EventEmitter


# ── helpers ───────────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _generate_pred_id() -> str:
    return f"pred_{uuid.uuid4().hex[:12]}"


def _generate_outcome_id() -> str:
    return f"outcome_{uuid.uuid4().hex[:12]}"


# ── input type ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionInput:
    """Minimal input to PredictionPipeline.predict().

    Phase 8 will produce this from real SessionState via a thin adapter.
    The pipeline logic does not change when that adapter is introduced.

    prior_step_per_signal must contain all six signal names if set; partial
    populations are rejected with ValueError to catch upstream bugs early.
    """

    session_id: str
    cycle_id: str
    step_id: str
    prior_step_composites: list[float]
    prior_step_per_signal: dict[str, float] | None
    cycle_config_defaults: dict[str, float] | None = None


# ── records ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionRecord:
    prediction_id: str
    session_id: str
    cycle_id: str
    step_id: str
    expected_composite_score: float
    expected_per_signal: dict[str, float]
    prediction_basis: str  # "prior_step_trajectory" | "cycle_config_default" | "static_baseline"
    confidence: float
    made_at: int


@dataclass(frozen=True)
class OutcomeRecord:
    outcome_id: str
    prediction_id: str
    session_id: str
    cycle_id: str
    step_id: str
    actual_composite_score: float
    prediction_error: float  # actual - expected (signed)
    error_classification: str  # "noise" | "notable" | "severe"
    per_signal_error: dict[str, float]
    recorded_at: int


# ── pipeline ──────────────────────────────────────────────────────────────────


class PredictionPipeline:
    """Deterministic prediction and outcome computation.

    No LLM dependency. All logic is arithmetic against prior cycle state
    and EvaluationComposer outputs.
    """

    def __init__(self, composer: EvaluationComposer) -> None:
        """Composer reference lets predictions use the same weights as evaluations."""
        self.composer = composer

    def predict(self, input: PredictionInput) -> PredictionRecord:
        """Compute expected scores using the most informed available basis."""
        basis, expected_per_signal, confidence = self._select_basis(input)
        expected_composite = self._compose_expected(expected_per_signal)
        return PredictionRecord(
            prediction_id=_generate_pred_id(),
            session_id=input.session_id,
            cycle_id=input.cycle_id,
            step_id=input.step_id,
            expected_composite_score=expected_composite,
            expected_per_signal=expected_per_signal,
            prediction_basis=basis,
            confidence=confidence,
            made_at=_now_ms(),
        )

    def resolve(
        self,
        prediction: PredictionRecord,
        evaluation: EvaluationPacket,
    ) -> OutcomeRecord:
        """Compare actual evaluation to prediction, classify error."""
        if prediction.step_id != evaluation.step_id:
            raise ValueError(
                f"Prediction step_id {prediction.step_id!r} != "
                f"evaluation step_id {evaluation.step_id!r}"
            )
        error = evaluation.composite_score - prediction.expected_composite_score
        classification = self._classify_error(abs(error))
        per_signal_error = {
            name: evaluation.per_signal_scores[name]
            - prediction.expected_per_signal.get(name, 0.65)
            for name in SIGNAL_NAMES
        }
        return OutcomeRecord(
            outcome_id=_generate_outcome_id(),
            prediction_id=prediction.prediction_id,
            session_id=prediction.session_id,
            cycle_id=prediction.cycle_id,
            step_id=prediction.step_id,
            actual_composite_score=evaluation.composite_score,
            prediction_error=error,
            error_classification=classification,
            per_signal_error=per_signal_error,
            recorded_at=_now_ms(),
        )

    def _select_basis(
        self, input: PredictionInput
    ) -> tuple[str, dict[str, float], float]:
        """Pick the most informed basis. Returns (basis, per_signal, confidence)."""
        if input.prior_step_per_signal is not None:
            missing = SIGNAL_NAMES - set(input.prior_step_per_signal.keys())
            if missing:
                raise ValueError(
                    f"prior_step_per_signal is incomplete — missing signals: {missing}"
                )
            confidence = 0.8 if len(input.prior_step_composites) >= 2 else 0.6
            return "prior_step_trajectory", dict(input.prior_step_per_signal), confidence

        if input.cycle_config_defaults is not None:
            return "cycle_config_default", dict(input.cycle_config_defaults), 0.7

        baseline = dict.fromkeys(SIGNAL_NAMES, 0.65)
        return "static_baseline", baseline, 0.5

    def _compose_expected(self, expected_per_signal: dict[str, float]) -> float:
        """Compose expected per-signal scores using the composer's weights."""
        return max(
            0.0,
            min(
                1.0,
                sum(
                    expected_per_signal[name] * weight
                    for name, weight in self.composer.weights.items()
                ),
            ),
        )

    def _classify_error(self, abs_error: float) -> str:
        """Classify error by PREDICTION_ERROR_CLASSIFIERS thresholds (absolute value)."""
        if abs_error < PREDICTION_ERROR_CLASSIFIERS["noise"]:
            return "noise"
        if abs_error < PREDICTION_ERROR_CLASSIFIERS["notable"]:
            return "notable"
        return "severe"


# ── persistence ───────────────────────────────────────────────────────────────


def write_prediction(db_path: Path, record: PredictionRecord) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO predictions
                (prediction_id, session_id, cycle_id, step_id,
                 expected_composite_score, expected_per_signal,
                 prediction_basis, confidence, made_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.prediction_id,
                record.session_id,
                record.cycle_id,
                record.step_id,
                record.expected_composite_score,
                json.dumps(record.expected_per_signal),
                record.prediction_basis,
                record.confidence,
                record.made_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def write_outcome(db_path: Path, record: OutcomeRecord) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO outcomes
                (outcome_id, prediction_id, session_id, cycle_id, step_id,
                 actual_composite_score, prediction_error, error_classification,
                 per_signal_error, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.outcome_id,
                record.prediction_id,
                record.session_id,
                record.cycle_id,
                record.step_id,
                record.actual_composite_score,
                record.prediction_error,
                record.error_classification,
                json.dumps(record.per_signal_error),
                record.recorded_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_predictions_for_session(
    db_path: Path, session_id: str
) -> list[PredictionRecord]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE session_id = ? ORDER BY made_at",
            (session_id,),
        ).fetchall()
        return [
            PredictionRecord(
                prediction_id=row["prediction_id"],
                session_id=row["session_id"],
                cycle_id=row["cycle_id"],
                step_id=row["step_id"],
                expected_composite_score=row["expected_composite_score"],
                expected_per_signal=json.loads(row["expected_per_signal"]),
                prediction_basis=row["prediction_basis"],
                confidence=row["confidence"],
                made_at=row["made_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


def read_outcomes_for_session(db_path: Path, session_id: str) -> list[OutcomeRecord]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM outcomes WHERE session_id = ? ORDER BY recorded_at",
            (session_id,),
        ).fetchall()
        return [
            OutcomeRecord(
                outcome_id=row["outcome_id"],
                prediction_id=row["prediction_id"],
                session_id=row["session_id"],
                cycle_id=row["cycle_id"],
                step_id=row["step_id"],
                actual_composite_score=row["actual_composite_score"],
                prediction_error=row["prediction_error"],
                error_classification=row["error_classification"],
                per_signal_error=json.loads(row["per_signal_error"]),
                recorded_at=row["recorded_at"],
            )
            for row in rows
        ]
    finally:
        conn.close()


# ── event emission helpers ────────────────────────────────────────────────────


def emit_prediction_made(
    emitter: EventEmitter,
    prediction: PredictionRecord,
    step_started_event_id: bytes,
) -> bytes:
    """Emit PredictionMade event chained to StepStarted."""
    return emitter.emit_cycle_event(
        event_type="PredictionMade",
        payload={
            "session_id": prediction.session_id,
            "cycle_id": prediction.cycle_id,
            "step_id": prediction.step_id,
            "prediction_id": prediction.prediction_id,
            "expected_composite_score": prediction.expected_composite_score,
            "expected_per_signal": prediction.expected_per_signal,
            "prediction_basis": prediction.prediction_basis,
            "confidence": prediction.confidence,
            "made_at": prediction.made_at,
        },
        causation_id=step_started_event_id,
        indexed_tags={"prediction_basis": prediction.prediction_basis},
    )


def emit_outcome_recorded(
    emitter: EventEmitter,
    outcome: OutcomeRecord,
    evaluation_composed_event_id: bytes,
) -> tuple[bytes, bytes | None]:
    """Emit OutcomeRecorded; if severe, also emit PredictionSevereMiss.

    Returns (outcome_event_id, severe_miss_event_id_or_None).

    PredictionSevereMiss is causally chained to OutcomeRecorded (derived
    event pattern) rather than to EvaluationComposed.
    """
    outcome_event_id = emitter.emit_cycle_event(
        event_type="OutcomeRecorded",
        payload={
            "session_id": outcome.session_id,
            "cycle_id": outcome.cycle_id,
            "step_id": outcome.step_id,
            "outcome_id": outcome.outcome_id,
            "prediction_id": outcome.prediction_id,
            "actual_composite_score": outcome.actual_composite_score,
            "prediction_error": outcome.prediction_error,
            "error_classification": outcome.error_classification,
            "per_signal_error": outcome.per_signal_error,
            "recorded_at": outcome.recorded_at,
        },
        causation_id=evaluation_composed_event_id,
        indexed_tags={"error_classification": outcome.error_classification},
    )

    severe_event_id: bytes | None = None
    if outcome.error_classification == "severe":
        expected = outcome.actual_composite_score - outcome.prediction_error
        severe_event_id = emitter.emit_cycle_event(
            event_type="PredictionSevereMiss",
            payload={
                "session_id": outcome.session_id,
                "cycle_id": outcome.cycle_id,
                "step_id": outcome.step_id,
                "outcome_id": outcome.outcome_id,
                "prediction_error": outcome.prediction_error,
                "expected": expected,
                "actual": outcome.actual_composite_score,
            },
            causation_id=outcome_event_id,
        )

    return outcome_event_id, severe_event_id
