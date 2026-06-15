"""End-to-end integration test for the prediction/outcome pipeline.

Tests the full predict → resolve → emit → persist → read cycle against
a real FossicStore and SQLite vault. No LLM calls — pipeline is deterministic.
"""

from __future__ import annotations

import itertools
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
    read_outcomes_for_session,
    read_predictions_for_session,
    write_outcome,
    write_prediction,
)
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

_SEQ = itertools.count()

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    db_path = tmp_path / "cerebra.db"
    db_path.touch()
    run_migrations(db_path)
    return tmp_path


@pytest.fixture()
def db_path(vault: Path) -> Path:
    return vault / "cerebra.db"


@pytest.fixture()
def store(vault: Path) -> FossicStore:
    return FossicStore(vault)


@pytest.fixture()
def composer() -> EvaluationComposer:
    return EvaluationComposer()


@pytest.fixture()
def pipeline(composer: EvaluationComposer) -> PredictionPipeline:
    return PredictionPipeline(composer)


def _fake_evaluation(step_id: str, composite: float) -> EvaluationPacket:
    per_signal = {name: composite for name in SIGNAL_NAMES}
    return EvaluationPacket(
        evaluation_id=f"eval_{next(_SEQ)}",
        session_id="sess_e2e",
        cycle_id="cycle_e2e",
        step_id=step_id,
        composite_score=composite,
        per_signal_scores=per_signal,
        weights_used=dict(SIGNAL_DEFAULT_WEIGHTS),
        composite_floor_violated=composite < 0.30,
        confidence=0.9,
        composed_at=1000000000000 + next(_SEQ),
    )


# ── full pipeline E2E ─────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPredictionPipelineE2E:
    def test_static_baseline_predict_resolve_emit_persist(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        pipeline: PredictionPipeline,
    ) -> None:
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_e2e")

        # 1. Emit a synthetic StepStarted event
        step_event_id = emitter.emit_cycle_event(
            event_type="StepStarted",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_e2e", "step_id": "step_e2e", "_seq": next(_SEQ)},
        )

        # 2. Predict with no prior data → static_baseline
        inp = PredictionInput(
            session_id="sess_e2e",
            cycle_id="cycle_e2e",
            step_id="step_e2e",
            prior_step_composites=[],
            prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        assert pred.prediction_basis == "static_baseline"
        assert pred.confidence == 0.5

        # 3. Emit PredictionMade chained to StepStarted
        pred_event_id = emit_prediction_made(emitter, pred, step_event_id)
        assert isinstance(pred_event_id, bytes)

        # 4. Persist prediction
        write_prediction(db_path, pred)

        # 5. Simulate evaluation — known composite
        ev = _fake_evaluation("step_e2e", 0.45)

        # 6. Emit synthetic EvaluationComposed event
        eval_event_id = emitter.emit_cycle_event(
            event_type="EvaluationComposed",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_e2e", "step_id": "step_e2e", "_seq": next(_SEQ)},
            causation_id=pred_event_id,
        )

        # 7. Resolve prediction vs evaluation
        out = pipeline.resolve(pred, ev)
        assert out.prediction_id == pred.prediction_id
        assert out.step_id == "step_e2e"
        expected_error = 0.45 - pred.expected_composite_score
        assert abs(out.prediction_error - expected_error) < 1e-9

        # 8. Emit OutcomeRecorded (+ PredictionSevereMiss if severe)
        outcome_event_id, severe_event_id = emit_outcome_recorded(emitter, out, eval_event_id)
        assert isinstance(outcome_event_id, bytes)
        if out.error_classification == "severe":
            assert severe_event_id is not None
        else:
            assert severe_event_id is None

        # 9. Persist outcome
        write_outcome(db_path, out)

        # 10. Read back and verify
        preds = read_predictions_for_session(db_path, "sess_e2e")
        assert len(preds) == 1
        assert preds[0].prediction_id == pred.prediction_id

        outcomes = read_outcomes_for_session(db_path, "sess_e2e")
        assert len(outcomes) == 1
        assert outcomes[0].outcome_id == out.outcome_id
        assert outcomes[0].prediction_id == pred.prediction_id

    def test_causation_chain_on_cycle_stream(
        self,
        vault: Path,
        store: FossicStore,
        pipeline: PredictionPipeline,
    ) -> None:
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_chain")

        step_event_id = emitter.emit_cycle_event(
            event_type="StepStarted",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_chain", "step_id": "step_chain", "_seq": next(_SEQ)},
        )

        inp = PredictionInput(
            session_id="sess_e2e",
            cycle_id="cycle_chain",
            step_id="step_chain",
            prior_step_composites=[],
            prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        pred_event_id = emit_prediction_made(emitter, pred, step_event_id)

        eval_event_id = emitter.emit_cycle_event(
            event_type="EvaluationComposed",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_chain", "step_id": "step_chain", "_seq": next(_SEQ)},
            causation_id=pred_event_id,
        )

        ev = _fake_evaluation("step_chain", 0.72)
        out = pipeline.resolve(pred, ev)
        emit_outcome_recorded(emitter, out, eval_event_id)

        # Verify events on the cycle stream
        stream_id = "cerebra/agent-trace/sess_e2e"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))
        event_types = [e.event_type for e in events]

        assert "StepStarted" in event_types
        assert "PredictionMade" in event_types
        assert "EvaluationComposed" in event_types
        assert "OutcomeRecorded" in event_types

        # Verify causation: PredictionMade → StepStarted
        pm = next(e for e in events if e.event_type == "PredictionMade")
        assert pm.causation_id is not None
        assert pm.causation_id.as_bytes() == step_event_id

        # Verify causation: OutcomeRecorded → EvaluationComposed
        or_ev = next(e for e in events if e.event_type == "OutcomeRecorded")
        assert or_ev.causation_id is not None
        assert or_ev.causation_id.as_bytes() == eval_event_id

    def test_severe_miss_full_chain(
        self,
        vault: Path,
        store: FossicStore,
        pipeline: PredictionPipeline,
    ) -> None:
        emitter = EventEmitter(store=store, session_id="sess_e2e", cycle_id="cycle_smiss_e2e")

        step_event_id = emitter.emit_cycle_event(
            event_type="StepStarted",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_smiss_e2e", "step_id": "step_sm", "_seq": next(_SEQ)},
        )

        inp = PredictionInput(
            session_id="sess_e2e",
            cycle_id="cycle_smiss_e2e",
            step_id="step_sm",
            prior_step_composites=[],
            prior_step_per_signal=None,
        )
        pred = pipeline.predict(inp)
        pred_event_id = emit_prediction_made(emitter, pred, step_event_id)

        eval_event_id = emitter.emit_cycle_event(
            event_type="EvaluationComposed",
            payload={"session_id": "sess_e2e", "cycle_id": "cycle_smiss_e2e", "step_id": "step_sm", "_seq": next(_SEQ)},
            causation_id=pred_event_id,
        )

        # Force severe error: actual 0.10 vs expected ~0.65 → error ~-0.55
        ev = _fake_evaluation("step_sm", 0.10)
        out = pipeline.resolve(pred, ev)
        assert out.error_classification == "severe"

        outcome_event_id, severe_event_id = emit_outcome_recorded(emitter, out, eval_event_id)
        assert severe_event_id is not None

        stream_id = "cerebra/agent-trace/sess_e2e"
        from fossic import ReadQuery
        events = store._store.read_range(ReadQuery(stream_id=stream_id))

        sm_events = [e for e in events if e.event_type == "PredictionSevereMiss"]
        assert len(sm_events) == 1

        # PredictionSevereMiss causation → OutcomeRecorded (not EvaluationComposed)
        assert sm_events[0].causation_id is not None
        assert sm_events[0].causation_id.as_bytes() == outcome_event_id

        payload = sm_events[0].payload()
        assert "expected" in payload
        assert "actual" in payload
        assert abs(payload["actual"] - 0.10) < 1e-9
