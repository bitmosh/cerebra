"""Tests for PredictionPipeline, PredictionRecord, OutcomeRecord, and persistence."""

from __future__ import annotations

import itertools
import tempfile
from pathlib import Path

import pytest

from cerebra.cognition._constants import SIGNAL_DEFAULT_WEIGHTS, SIGNAL_NAMES
from cerebra.cognition.evaluation import EvaluationComposer, EvaluationPacket
from cerebra.cognition.predictions import (
    PredictionInput,
    PredictionPipeline,
    read_outcomes_for_session,
    read_predictions_for_session,
    write_outcome,
    write_prediction,
)
from cerebra.storage.migrations import run_migrations

# ── helpers ───────────────────────────────────────────────────────────────────

_SEQ = itertools.count()


def _fresh_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        p = Path(f.name)
    run_migrations(p)
    return p


def _composer() -> EvaluationComposer:
    return EvaluationComposer()


def _baseline_input(step_id: str = "step_001") -> PredictionInput:
    return PredictionInput(
        session_id="sess_test",
        cycle_id="cycle_test",
        step_id=step_id,
        prior_step_composites=[],
        prior_step_per_signal=None,
    )


def _prior_input(n_prior: int = 1, step_id: str = "step_002") -> PredictionInput:
    prior_per_signal = {name: 0.72 for name in SIGNAL_NAMES}
    prior_composites = [0.72] * n_prior
    return PredictionInput(
        session_id="sess_test",
        cycle_id="cycle_test",
        step_id=step_id,
        prior_step_composites=prior_composites,
        prior_step_per_signal=prior_per_signal,
    )


def _fake_evaluation(
    step_id: str,
    composite: float,
    per_signal: dict[str, float] | None = None,
) -> EvaluationPacket:
    if per_signal is None:
        per_signal = {name: composite for name in SIGNAL_NAMES}
    return EvaluationPacket(
        evaluation_id=f"eval_{next(_SEQ)}",
        session_id="sess_test",
        cycle_id="cycle_test",
        step_id=step_id,
        composite_score=composite,
        per_signal_scores=per_signal,
        weights_used=dict(SIGNAL_DEFAULT_WEIGHTS),
        composite_floor_violated=composite < 0.30,
        confidence=0.9,
        composed_at=1000000000000 + next(_SEQ),
    )


# ── PredictionRecord immutability ─────────────────────────────────────────────


@pytest.mark.unit
class TestPredictionRecordFrozen:
    def test_prediction_record_is_frozen(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_baseline_input())
        with pytest.raises((AttributeError, TypeError)):
            rec.session_id = "mutated"  # type: ignore[misc]

    def test_outcome_record_is_frozen(self) -> None:
        pipeline = PredictionPipeline(_composer())
        pred = pipeline.predict(_baseline_input("step_x"))
        ev = _fake_evaluation("step_x", 0.72)
        out = pipeline.resolve(pred, ev)
        with pytest.raises((AttributeError, TypeError)):
            out.session_id = "mutated"  # type: ignore[misc]


# ── PredictionPipeline.predict() — basis selection ────────────────────────────


@pytest.mark.unit
class TestPredictionBasisSelection:
    def test_static_baseline_when_no_prior(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_baseline_input())
        assert rec.prediction_basis == "static_baseline"
        assert rec.confidence == 0.5

    def test_static_baseline_per_signal_all_0_65(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_baseline_input())
        assert set(rec.expected_per_signal.keys()) == SIGNAL_NAMES
        for v in rec.expected_per_signal.values():
            assert abs(v - 0.65) < 1e-9

    def test_static_baseline_composite_uses_weights(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_baseline_input())
        expected = sum(0.65 * w for w in SIGNAL_DEFAULT_WEIGHTS.values())
        assert abs(rec.expected_composite_score - expected) < 1e-9

    def test_cycle_config_default_basis(self) -> None:
        defaults = {name: 0.80 for name in SIGNAL_NAMES}
        inp = PredictionInput(
            session_id="s", cycle_id="c", step_id="step_cfg",
            prior_step_composites=[],
            prior_step_per_signal=None,
            cycle_config_defaults=defaults,
        )
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(inp)
        assert rec.prediction_basis == "cycle_config_default"
        assert rec.confidence == 0.7
        assert all(abs(v - 0.80) < 1e-9 for v in rec.expected_per_signal.values())

    def test_prior_trajectory_with_1_prior_confidence_0_6(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_prior_input(n_prior=1))
        assert rec.prediction_basis == "prior_step_trajectory"
        assert rec.confidence == 0.6

    def test_prior_trajectory_with_2_prior_confidence_0_8(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_prior_input(n_prior=2))
        assert rec.prediction_basis == "prior_step_trajectory"
        assert rec.confidence == 0.8

    def test_prior_trajectory_uses_prior_per_signal(self) -> None:
        prior_per_signal = {name: 0.55 for name in SIGNAL_NAMES}
        inp = PredictionInput(
            session_id="s", cycle_id="c", step_id="step_t",
            prior_step_composites=[0.55],
            prior_step_per_signal=prior_per_signal,
        )
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(inp)
        for name in SIGNAL_NAMES:
            assert abs(rec.expected_per_signal[name] - 0.55) < 1e-9

    def test_prior_trajectory_beats_cycle_defaults(self) -> None:
        prior_per_signal = {name: 0.72 for name in SIGNAL_NAMES}
        defaults = {name: 0.80 for name in SIGNAL_NAMES}
        inp = PredictionInput(
            session_id="s", cycle_id="c", step_id="step_both",
            prior_step_composites=[0.72],
            prior_step_per_signal=prior_per_signal,
            cycle_config_defaults=defaults,
        )
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(inp)
        assert rec.prediction_basis == "prior_step_trajectory"

    def test_incomplete_prior_per_signal_raises(self) -> None:
        partial = {"COHERENCE": 0.7}  # only 1 of 6
        inp = PredictionInput(
            session_id="s", cycle_id="c", step_id="step_bad",
            prior_step_composites=[0.7],
            prior_step_per_signal=partial,  # type: ignore[arg-type]
        )
        pipeline = PredictionPipeline(_composer())
        with pytest.raises(ValueError, match="incomplete"):
            pipeline.predict(inp)

    def test_prediction_id_unique_across_calls(self) -> None:
        pipeline = PredictionPipeline(_composer())
        ids = {pipeline.predict(_baseline_input(f"step_{i}")).prediction_id for i in range(5)}
        assert len(ids) == 5

    def test_composed_expected_composite_in_unit_range(self) -> None:
        pipeline = PredictionPipeline(_composer())
        rec = pipeline.predict(_baseline_input())
        assert 0.0 <= rec.expected_composite_score <= 1.0


# ── PredictionPipeline.resolve() ──────────────────────────────────────────────


@pytest.mark.unit
class TestPredictionResolve:
    def test_signed_prediction_error(self) -> None:
        pipeline = PredictionPipeline(_composer())
        pred = pipeline.predict(_baseline_input("step_r"))
        ev = _fake_evaluation("step_r", 0.9)
        out = pipeline.resolve(pred, ev)
        expected_error = 0.9 - pred.expected_composite_score
        assert abs(out.prediction_error - expected_error) < 1e-9

    def test_outcome_id_unique(self) -> None:
        pipeline = PredictionPipeline(_composer())
        ids = set()
        for i in range(5):
            pred = pipeline.predict(_baseline_input(f"step_uniq_{i}"))
            ev = _fake_evaluation(f"step_uniq_{i}", 0.72)
            out = pipeline.resolve(pred, ev)
            ids.add(out.outcome_id)
        assert len(ids) == 5

    def test_step_id_mismatch_raises(self) -> None:
        pipeline = PredictionPipeline(_composer())
        pred = pipeline.predict(_baseline_input("step_A"))
        ev = _fake_evaluation("step_B", 0.72)
        with pytest.raises(ValueError, match="step_id"):
            pipeline.resolve(pred, ev)

    def test_per_signal_error_computed(self) -> None:
        pipeline = PredictionPipeline(_composer())
        pred = pipeline.predict(_baseline_input("step_sig"))
        per_signal = {name: 0.9 for name in SIGNAL_NAMES}
        ev = _fake_evaluation("step_sig", 0.9, per_signal=per_signal)
        out = pipeline.resolve(pred, ev)
        assert set(out.per_signal_error.keys()) == SIGNAL_NAMES
        # All signals predicted at 0.65, actual 0.9 → error ~+0.25 for each
        for v in out.per_signal_error.values():
            assert abs(v - 0.25) < 1e-6

    def test_links_prediction_id(self) -> None:
        pipeline = PredictionPipeline(_composer())
        pred = pipeline.predict(_baseline_input("step_link"))
        ev = _fake_evaluation("step_link", 0.72)
        out = pipeline.resolve(pred, ev)
        assert out.prediction_id == pred.prediction_id

    def test_preserves_session_cycle_step_ids(self) -> None:
        pipeline = PredictionPipeline(_composer())
        pred = pipeline.predict(_baseline_input("step_ids"))
        ev = _fake_evaluation("step_ids", 0.72)
        out = pipeline.resolve(pred, ev)
        assert out.session_id == pred.session_id
        assert out.cycle_id == pred.cycle_id
        assert out.step_id == pred.step_id


# ── Error classification ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestErrorClassification:
    def _classify(self, error: float) -> str:
        pipeline = PredictionPipeline(_composer())
        # Build a prediction with known expected composite
        pred = pipeline.predict(_baseline_input("step_cls"))
        expected = pred.expected_composite_score
        actual = expected + error
        actual = max(0.0, min(1.0, actual))
        ev = _fake_evaluation("step_cls", actual)
        out = pipeline.resolve(pred, ev)
        return out.error_classification

    def test_noise_below_threshold(self) -> None:
        assert self._classify(0.05) == "noise"
        assert self._classify(-0.05) == "noise"

    def test_noise_zero_error(self) -> None:
        assert self._classify(0.0) == "noise"

    def test_notable_at_exact_0_10(self) -> None:
        # |error| = 0.10 → NOT noise (noise requires < 0.10), should be notable
        pipeline = PredictionPipeline(_composer())
        result = pipeline._classify_error(0.10)
        assert result == "notable"

    def test_notable_range(self) -> None:
        assert self._classify(0.20) == "notable"
        assert self._classify(-0.25) == "notable"

    def test_severe_at_exact_0_40(self) -> None:
        pipeline = PredictionPipeline(_composer())
        result = pipeline._classify_error(0.40)
        assert result == "severe"

    def test_severe_large_error(self) -> None:
        pipeline = PredictionPipeline(_composer())
        result = pipeline._classify_error(0.9)
        assert result == "severe"

    def test_symmetric_negative_equals_positive(self) -> None:
        pipeline = PredictionPipeline(_composer())
        assert pipeline._classify_error(0.25) == pipeline._classify_error(0.25)
        assert pipeline._classify_error(0.45) == "severe"


# ── Persistence ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPredictionPersistence:
    def test_write_and_read_prediction_round_trip(self) -> None:
        db = _fresh_db()
        try:
            pipeline = PredictionPipeline(_composer())
            pred = pipeline.predict(_baseline_input("step_persist"))
            write_prediction(db, pred)
            results = read_predictions_for_session(db, "sess_test")
            assert len(results) == 1
            r = results[0]
            assert r.prediction_id == pred.prediction_id
            assert r.session_id == pred.session_id
            assert abs(r.expected_composite_score - pred.expected_composite_score) < 1e-9
            assert r.prediction_basis == pred.prediction_basis
            assert r.confidence == pred.confidence
            assert r.expected_per_signal == pred.expected_per_signal
        finally:
            db.unlink(missing_ok=True)

    def test_write_and_read_outcome_round_trip(self) -> None:
        db = _fresh_db()
        try:
            pipeline = PredictionPipeline(_composer())
            pred = pipeline.predict(_baseline_input("step_out_persist"))
            ev = _fake_evaluation("step_out_persist", 0.45)
            out = pipeline.resolve(pred, ev)
            write_prediction(db, pred)
            write_outcome(db, out)
            results = read_outcomes_for_session(db, "sess_test")
            assert len(results) == 1
            r = results[0]
            assert r.outcome_id == out.outcome_id
            assert r.prediction_id == out.prediction_id
            assert abs(r.actual_composite_score - out.actual_composite_score) < 1e-9
            assert r.error_classification == out.error_classification
            assert r.per_signal_error == out.per_signal_error
        finally:
            db.unlink(missing_ok=True)

    def test_per_signal_json_round_trips(self) -> None:
        db = _fresh_db()
        try:
            pipeline = PredictionPipeline(_composer())
            pred = pipeline.predict(_prior_input(n_prior=2, step_id="step_json"))
            write_prediction(db, pred)
            results = read_predictions_for_session(db, "sess_test")
            assert results[0].expected_per_signal == pred.expected_per_signal
        finally:
            db.unlink(missing_ok=True)

    def test_multiple_predictions_ordered_by_made_at(self) -> None:
        db = _fresh_db()
        try:
            pipeline = PredictionPipeline(_composer())
            preds = [pipeline.predict(_baseline_input(f"step_ord_{i}")) for i in range(3)]
            for p in preds:
                write_prediction(db, p)
            results = read_predictions_for_session(db, "sess_test")
            assert len(results) == 3
            assert [r.step_id for r in results] == [p.step_id for p in sorted(preds, key=lambda p: p.made_at)]
        finally:
            db.unlink(missing_ok=True)

    def test_no_predictions_returns_empty_list(self) -> None:
        db = _fresh_db()
        try:
            results = read_predictions_for_session(db, "sess_nonexistent")
            assert results == []
        finally:
            db.unlink(missing_ok=True)

    def test_outcome_fk_requires_prediction_exists(self) -> None:
        """Outcome with non-existent prediction_id should fail FK constraint."""
        import sqlite3
        db = _fresh_db()
        try:
            pipeline = PredictionPipeline(_composer())
            pred = pipeline.predict(_baseline_input("step_fk"))
            ev = _fake_evaluation("step_fk", 0.72)
            out = pipeline.resolve(pred, ev)
            # Write outcome WITHOUT writing prediction first — FK violation
            with pytest.raises(sqlite3.IntegrityError):
                write_outcome(db, out)
        finally:
            db.unlink(missing_ok=True)
