"""Tests for prediction/outcome event emission helpers."""

from __future__ import annotations

import itertools
import tempfile
from pathlib import Path

import pytest

from cerebra.cognition._constants import SIGNAL_DEFAULT_WEIGHTS, SIGNAL_NAMES
from cerebra.cognition.evaluation import EvaluationComposer, EvaluationPacket
from cerebra.cognition.event_emitter import EventEmitter
from cerebra.cognition.predictions import (
    PredictionInput,
    PredictionPipeline,
    emit_outcome_recorded,
    emit_prediction_made,
)
from cerebra.storage.fossic_store import FossicStore

# ── helpers ───────────────────────────────────────────────────────────────────

_SEQ = itertools.count()


def _temp_vault() -> Path:
    d = Path(tempfile.mkdtemp())
    return d


def _composer() -> EvaluationComposer:
    return EvaluationComposer()


def _fake_evaluation(step_id: str, composite: float) -> EvaluationPacket:
    per_signal = dict.fromkeys(SIGNAL_NAMES, composite)
    return EvaluationPacket(
        evaluation_id=f"eval_{next(_SEQ)}",
        session_id="sess_001",
        cycle_id="cycle_001",
        step_id=step_id,
        composite_score=composite,
        per_signal_scores=per_signal,
        weights_used=dict(SIGNAL_DEFAULT_WEIGHTS),
        composite_floor_violated=composite < 0.30,
        confidence=0.9,
        composed_at=1000000000000 + next(_SEQ),
    )


def _make_emitter(vault: Path, cycle_id: str = "cycle_001") -> EventEmitter:
    store = FossicStore(vault)
    return EventEmitter(store=store, session_id="sess_001", cycle_id=cycle_id)


def _emit_stub_event(emitter: EventEmitter) -> bytes:
    return emitter.emit_cycle_event(
        event_type="StepStarted",
        payload={"session_id": "sess_001", "cycle_id": "cycle_001", "step_id": "step_001", "_seq": next(_SEQ)},
    )


def _emit_eval_event(emitter: EventEmitter, causation_id: bytes) -> bytes:
    return emitter.emit_cycle_event(
        event_type="EvaluationComposed",
        payload={"session_id": "sess_001", "cycle_id": "cycle_001", "step_id": "step_001", "_seq": next(_SEQ)},
        causation_id=causation_id,
    )


# ── PredictionMade emission ───────────────────────────────────────────────────


@pytest.mark.unit
class TestEmitPredictionMade:
    def test_emit_returns_bytes(self) -> None:
        vault = _temp_vault()
        emitter = _make_emitter(vault)
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_001", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        event_id = emit_prediction_made(emitter, pred, step_event_id)
        assert isinstance(event_id, bytes)
        assert len(event_id) > 0

    def test_prediction_made_payload_contains_required_fields(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_emit")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_emit", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        emit_prediction_made(emitter, pred, step_event_id)

        # Read events from the stream and find PredictionMade
        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        pm_events = [e for e in events if e.event_type == "PredictionMade"]
        assert len(pm_events) == 1

        payload = pm_events[0].payload()
        assert payload["prediction_id"] == pred.prediction_id
        assert payload["session_id"] == "sess_001"
        assert payload["step_id"] == "step_001"
        assert "expected_composite_score" in payload
        assert "expected_per_signal" in payload
        assert "prediction_basis" in payload
        assert "confidence" in payload

    def test_prediction_made_indexed_tags(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_tags")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_tags", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        emit_prediction_made(emitter, pred, step_event_id)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        pm_events = [e for e in events if e.event_type == "PredictionMade"]
        tags = pm_events[0].indexed_tags()
        assert tags.get("prediction_basis") == "static_baseline"

    def test_prediction_made_causation_is_step_started(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_cause")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_cause", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        emit_prediction_made(emitter, pred, step_event_id)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        pm_events = [e for e in events if e.event_type == "PredictionMade"]
        assert pm_events[0].causation_id is not None
        assert pm_events[0].causation_id.as_bytes() == step_event_id

    def test_two_predictions_back_to_back_emit_separately(self) -> None:
        """CCE dedup risk: unique prediction_ids ensure no collapse."""
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_two")
        pipeline = PredictionPipeline(_composer())
        step_id1 = _emit_stub_event(emitter)

        inp1 = PredictionInput(
            session_id="sess_001", cycle_id="cycle_two", step_id="step_a",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        inp2 = PredictionInput(
            session_id="sess_001", cycle_id="cycle_two", step_id="step_b",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred1 = pipeline.predict(inp1)
        pred2 = pipeline.predict(inp2)

        eid1 = emit_prediction_made(emitter, pred1, step_id1)
        eid2 = emit_prediction_made(emitter, pred2, step_id1)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        pm_events = [e for e in events if e.event_type == "PredictionMade"]
        assert len(pm_events) == 2
        assert eid1 != eid2


# ── OutcomeRecorded emission ───────────────────────────────────────────────────


@pytest.mark.unit
class TestEmitOutcomeRecorded:
    def test_non_severe_returns_none_severe_event_id(self) -> None:
        vault = _temp_vault()
        emitter = _make_emitter(vault, "cycle_nonsevere")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        eval_event_id = _emit_eval_event(emitter, step_event_id)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_nonsevere", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        ev = _fake_evaluation("step_001", 0.70)  # close to baseline ~0.65 → noise
        out = pipeline.resolve(pred, ev)

        outcome_id, severe_id = emit_outcome_recorded(emitter, out, eval_event_id)
        assert isinstance(outcome_id, bytes)
        assert severe_id is None

    def test_severe_emits_severe_miss_event(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_severe")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        eval_event_id = _emit_eval_event(emitter, step_event_id)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_severe", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        # baseline expected ~0.65; actual 0.1 → |err| ~0.55 → severe
        ev = _fake_evaluation("step_001", 0.10)
        out = pipeline.resolve(pred, ev)
        assert out.error_classification == "severe"

        _, severe_id = emit_outcome_recorded(emitter, out, eval_event_id)
        assert severe_id is not None
        assert isinstance(severe_id, bytes)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        severe_events = [e for e in events if e.event_type == "PredictionSevereMiss"]
        assert len(severe_events) == 1

    def test_severe_miss_payload_fields(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_smiss")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        eval_event_id = _emit_eval_event(emitter, step_event_id)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_smiss", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        ev = _fake_evaluation("step_001", 0.10)
        out = pipeline.resolve(pred, ev)
        emit_outcome_recorded(emitter, out, eval_event_id)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        severe = [e for e in events if e.event_type == "PredictionSevereMiss"][0]
        payload = severe.payload()
        assert "prediction_error" in payload
        assert "expected" in payload
        assert "actual" in payload
        assert "outcome_id" in payload
        assert payload["actual"] == out.actual_composite_score

    def test_severe_miss_causation_is_outcome_recorded(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_scause")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        eval_event_id = _emit_eval_event(emitter, step_event_id)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_scause", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        ev = _fake_evaluation("step_001", 0.10)
        out = pipeline.resolve(pred, ev)
        outcome_id, _severe_id = emit_outcome_recorded(emitter, out, eval_event_id)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        severe = [e for e in events if e.event_type == "PredictionSevereMiss"][0]
        # Severe miss must chain to OutcomeRecorded, not EvaluationComposed
        assert severe.causation_id is not None
        assert severe.causation_id.as_bytes() == outcome_id

    def test_outcome_recorded_causation_is_evaluation_composed(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_orcause")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        eval_event_id = _emit_eval_event(emitter, step_event_id)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_orcause", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        ev = _fake_evaluation("step_001", 0.70)
        out = pipeline.resolve(pred, ev)
        emit_outcome_recorded(emitter, out, eval_event_id)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        or_events = [e for e in events if e.event_type == "OutcomeRecorded"]
        assert len(or_events) == 1
        assert or_events[0].causation_id is not None
        assert or_events[0].causation_id.as_bytes() == eval_event_id

    def test_outcome_recorded_indexed_tags(self) -> None:
        vault = _temp_vault()
        store = FossicStore(vault)
        emitter = EventEmitter(store=store, session_id="sess_001", cycle_id="cycle_ortags")
        pipeline = PredictionPipeline(_composer())
        step_event_id = _emit_stub_event(emitter)
        eval_event_id = _emit_eval_event(emitter, step_event_id)
        inp = PredictionInput(
            session_id="sess_001", cycle_id="cycle_ortags", step_id="step_001",
            prior_step_composites=[], prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        ev = _fake_evaluation("step_001", 0.70)
        out = pipeline.resolve(pred, ev)
        emit_outcome_recorded(emitter, out, eval_event_id)

        stream_id = "cerebra/agent-trace/sess_001"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        or_events = [e for e in events if e.event_type == "OutcomeRecorded"]
        tags = or_events[0].indexed_tags()
        assert "error_classification" in tags
