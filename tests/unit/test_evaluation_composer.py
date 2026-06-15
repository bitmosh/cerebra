"""Unit tests for EvaluationComposer and emit_evaluation_events helper."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from cerebra.cognition._constants import (
    COMPOSITE_SCORE_FLOOR,
    SIGNAL_DEFAULT_WEIGHTS,
    SIGNAL_NAMES,
)
from cerebra.cognition.evaluation import EvaluationComposer, EvaluationPacket, emit_evaluation_events
from cerebra.cognition.event_emitter import EventEmitter
from cerebra.cognition.signals import SignalScore
from cerebra.storage.fossic_store import FossicStore

# ── helpers ───────────────────────────────────────────────────────────────────

_SIGNAL_ORDER = [
    "COHERENCE", "GROUNDEDNESS", "GENERATIVITY",
    "RELEVANCE", "PRECISION", "EPISTEMIC_HUMILITY",
]

_SEQ = itertools.count()


def _make_scores(score: float = 0.8) -> list[SignalScore]:
    return [
        SignalScore(
            signal_name=name,
            score=score,
            evaluator_prompt_version=f"{name.lower()}_v1",
        )
        for name in _SIGNAL_ORDER
    ]


def _packet_from_scores(scores: list[SignalScore], **kwargs) -> EvaluationPacket:
    composer = EvaluationComposer()
    return composer.compose(
        scores,
        session_id=kwargs.get("session_id", "sess_001"),
        cycle_id=kwargs.get("cycle_id", "cycle_001"),
        step_id=kwargs.get("step_id", "step_001"),
    )


# ── composer tests ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEvaluationComposerWeights:
    def test_default_weights_sum_to_one(self) -> None:
        composer = EvaluationComposer()
        total = sum(composer.weights.values())
        assert abs(total - 1.0) < 0.001

    def test_default_weights_cover_all_signals(self) -> None:
        composer = EvaluationComposer()
        assert set(composer.weights.keys()) == SIGNAL_NAMES

    def test_custom_weights_accepted(self) -> None:
        custom = {k: 1.0 / 6 for k in SIGNAL_NAMES}
        composer = EvaluationComposer(weights=custom)
        assert abs(sum(composer.weights.values()) - 1.0) < 0.01

    def test_weights_not_summing_to_one_raise(self) -> None:
        bad = dict(SIGNAL_DEFAULT_WEIGHTS)
        bad["COHERENCE"] = 0.99  # blows up the sum
        with pytest.raises(ValueError, match="must sum to"):
            EvaluationComposer(weights=bad)

    def test_weights_missing_signal_raise(self) -> None:
        bad = dict(SIGNAL_DEFAULT_WEIGHTS)
        del bad["COHERENCE"]
        bad["COHERENCE_EXTRA"] = 0.18  # same weight, wrong name
        with pytest.raises(ValueError, match="Missing"):
            EvaluationComposer(weights=bad)


@pytest.mark.unit
class TestCompose:
    def test_composite_is_weighted_sum(self) -> None:
        scores = _make_scores(score=1.0)
        packet = _packet_from_scores(scores)
        expected = sum(SIGNAL_DEFAULT_WEIGHTS.values())  # all scores = 1.0
        assert packet.composite_score == pytest.approx(expected, abs=1e-6)

    def test_composite_in_range(self) -> None:
        for score_val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            packet = _packet_from_scores(_make_scores(score=score_val))
            assert 0.0 <= packet.composite_score <= 1.0

    def test_per_signal_scores_populated(self) -> None:
        scores = _make_scores(score=0.7)
        packet = _packet_from_scores(scores)
        assert set(packet.per_signal_scores.keys()) == SIGNAL_NAMES
        for name, val in packet.per_signal_scores.items():
            assert val == pytest.approx(0.7), f"{name}: expected 0.7 got {val}"

    def test_weights_used_matches_composer(self) -> None:
        composer = EvaluationComposer()
        packet = composer.compose(_make_scores(), "s", "c", "st")
        assert packet.weights_used == composer.weights

    def test_evaluation_id_generated(self) -> None:
        packet = _packet_from_scores(_make_scores())
        assert packet.evaluation_id.startswith("eval_")

    def test_session_cycle_step_ids_preserved(self) -> None:
        composer = EvaluationComposer()
        packet = composer.compose(
            _make_scores(), "my_session", "my_cycle", "my_step"
        )
        assert packet.session_id == "my_session"
        assert packet.cycle_id == "my_cycle"
        assert packet.step_id == "my_step"

    def test_composed_at_is_int(self) -> None:
        packet = _packet_from_scores(_make_scores())
        assert isinstance(packet.composed_at, int)
        assert packet.composed_at > 0

    def test_missing_signal_raises(self) -> None:
        incomplete = _make_scores()[:4]  # only 4 of 6
        composer = EvaluationComposer()
        with pytest.raises(ValueError, match="Missing signal"):
            composer.compose(incomplete, "s", "c", "st")


@pytest.mark.unit
class TestCompositeFloor:
    def test_floor_not_violated_above_threshold(self) -> None:
        high_scores = _make_scores(score=0.9)
        packet = _packet_from_scores(high_scores)
        assert packet.composite_floor_violated is False

    def test_floor_violated_below_threshold(self) -> None:
        low_scores = _make_scores(score=0.0)
        packet = _packet_from_scores(low_scores)
        assert packet.composite_floor_violated is True

    def test_floor_exactly_at_boundary(self) -> None:
        # Need to compute the exact per-signal score that gives composite = COMPOSITE_SCORE_FLOOR
        # Since all weights sum to 1.0 and all scores equal, composite = score
        scores = _make_scores(score=COMPOSITE_SCORE_FLOOR)
        packet = _packet_from_scores(scores)
        # At exactly the floor, floor_violated = score < floor = False
        assert packet.composite_floor_violated is False

    def test_floor_just_below_boundary(self) -> None:
        scores = _make_scores(score=COMPOSITE_SCORE_FLOOR - 0.01)
        packet = _packet_from_scores(scores)
        assert packet.composite_floor_violated is True


@pytest.mark.unit
class TestConfidence:
    def test_default_confidence_is_mean_signal_strength(self) -> None:
        scores = _make_scores()  # all signal_strength = 1.0
        packet = _packet_from_scores(scores)
        assert packet.confidence == pytest.approx(1.0)

    def test_partial_confidence(self) -> None:
        scores = [
            SignalScore(signal_name=name, score=0.8, evaluator_prompt_version="v1",
                        signal_strength=0.5)
            for name in _SIGNAL_ORDER
        ]
        packet = _packet_from_scores(scores)
        assert packet.confidence == pytest.approx(0.5)


# ── emit_evaluation_events tests ──────────────────────────────────────────────


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def emitter_and_seed(tmp_vault):
    store = FossicStore(tmp_vault)
    session_id = "sess_emit_test"
    cycle_id = f"cycle_{next(_SEQ)}"
    em = EventEmitter(store, session_id, cycle_id)
    # Emit a seed event to act as step_executed_event_id
    seed_id = em.emit_cycle_event(
        event_type="StepExecuted",
        payload={"session_id": session_id, "cycle_id": cycle_id, "step_id": "step_001",
                 "_seq": next(_SEQ)},
    )
    return em, seed_id, store, cycle_id


@pytest.mark.unit
class TestEmitEvaluationEvents:
    def test_emits_seven_events(self, emitter_and_seed) -> None:
        em, seed_id, store, cycle_id = emitter_and_seed
        scores = _make_scores()
        packet = _packet_from_scores(scores)

        emit_evaluation_events(em, scores, packet, seed_id)

        stream_id = "cerebra/agent-trace/sess_emit_test"
        events = store._store.read_range(
            __import__("fossic").ReadQuery(stream_id=stream_id, branch="main")
        )
        # 1 seed + 6 SignalEvaluated + 1 EvaluationComposed = 8
        assert len(events) == 8

    def test_returns_bytes_event_id(self, emitter_and_seed) -> None:
        em, seed_id, store, cycle_id = emitter_and_seed
        scores = _make_scores()
        packet = _packet_from_scores(scores)

        result = emit_evaluation_events(em, scores, packet, seed_id)
        assert isinstance(result, bytes)

    def test_signal_evaluated_event_types(self, emitter_and_seed) -> None:
        em, seed_id, store, cycle_id = emitter_and_seed
        scores = _make_scores()
        packet = _packet_from_scores(scores)

        emit_evaluation_events(em, scores, packet, seed_id)

        stream_id = "cerebra/agent-trace/sess_emit_test"
        events = store._store.read_range(
            __import__("fossic").ReadQuery(stream_id=stream_id, branch="main")
        )
        types = [e.event_type for e in events]
        assert types.count("SignalEvaluated") == 6
        assert types.count("EvaluationComposed") == 1
        assert types[-1] == "EvaluationComposed"

    def test_indexed_tags_signal_name(self, emitter_and_seed) -> None:
        em, seed_id, store, cycle_id = emitter_and_seed
        scores = _make_scores()
        packet = _packet_from_scores(scores)

        emit_evaluation_events(em, scores, packet, seed_id)

        stream_id = "cerebra/agent-trace/sess_emit_test"
        events = store._store.read_range(
            __import__("fossic").ReadQuery(stream_id=stream_id, branch="main")
        )
        signal_events = [e for e in events if e.event_type == "SignalEvaluated"]
        for ev in signal_events:
            tags = ev.indexed_tags()
            assert "signal_name" in tags

    def test_evaluation_composed_payload(self, emitter_and_seed) -> None:
        em, seed_id, store, cycle_id = emitter_and_seed
        scores = _make_scores()
        packet = _packet_from_scores(scores)

        emit_evaluation_events(em, scores, packet, seed_id)

        stream_id = "cerebra/agent-trace/sess_emit_test"
        events = store._store.read_range(
            __import__("fossic").ReadQuery(stream_id=stream_id, branch="main")
        )
        composed = [e for e in events if e.event_type == "EvaluationComposed"][0]
        payload = composed.payload()
        assert "composite_score" in payload
        assert "per_signal_scores" in payload
        assert "evaluation_id" in payload
