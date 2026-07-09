# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Phase 6 _constants.py additions."""

from __future__ import annotations

import pytest

from cerebra.cognition._constants import (
    CLUTCH_ACTIONS,
    COMPOSITE_SCORE_FLOOR,
    CYCLE_MAX_STEPS,
    LATTICE_SNAPSHOT_CADENCE,
    PHASE_6_EVENT_TYPES,
    PREDICTION_ERROR_CLASSIFIERS,
    RECURSION_DEPTH_DEFAULT,
    SIGNAL_DEFAULT_WEIGHTS,
    SIGNAL_NAMES,
)
from cerebra.inspector.event import (
    ALL_KNOWN_EVENT_TYPES,
)
from cerebra.inspector.event import (
    PHASE_6_EVENT_TYPES as INSPECTOR_PHASE_6_EVENT_TYPES,
)


@pytest.mark.unit
class TestSignalNames:
    def test_has_six_signals(self) -> None:
        assert len(SIGNAL_NAMES) == 6

    def test_contains_all_expected_signals(self) -> None:
        expected = {
            "COHERENCE",
            "GROUNDEDNESS",
            "GENERATIVITY",
            "RELEVANCE",
            "PRECISION",
            "EPISTEMIC_HUMILITY",
        }
        assert expected == SIGNAL_NAMES

    def test_is_frozenset(self) -> None:
        assert isinstance(SIGNAL_NAMES, frozenset)

    def test_matches_weight_keys(self) -> None:
        assert frozenset(SIGNAL_DEFAULT_WEIGHTS.keys()) == SIGNAL_NAMES


@pytest.mark.unit
class TestSignalDefaultWeights:
    def test_sum_to_one(self) -> None:
        total = sum(SIGNAL_DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_weights_positive(self) -> None:
        for name, w in SIGNAL_DEFAULT_WEIGHTS.items():
            assert w > 0, f"{name} weight must be positive"

    def test_all_weights_less_than_one(self) -> None:
        for name, w in SIGNAL_DEFAULT_WEIGHTS.items():
            assert w < 1.0, f"{name} weight must be <1.0"

    def test_coherence_weight(self) -> None:
        assert SIGNAL_DEFAULT_WEIGHTS["COHERENCE"] == pytest.approx(0.18)

    def test_groundedness_weight(self) -> None:
        assert SIGNAL_DEFAULT_WEIGHTS["GROUNDEDNESS"] == pytest.approx(0.18)

    def test_generativity_weight(self) -> None:
        assert SIGNAL_DEFAULT_WEIGHTS["GENERATIVITY"] == pytest.approx(0.12)

    def test_relevance_weight(self) -> None:
        assert SIGNAL_DEFAULT_WEIGHTS["RELEVANCE"] == pytest.approx(0.22)

    def test_precision_weight(self) -> None:
        assert SIGNAL_DEFAULT_WEIGHTS["PRECISION"] == pytest.approx(0.12)

    def test_epistemic_humility_weight(self) -> None:
        assert SIGNAL_DEFAULT_WEIGHTS["EPISTEMIC_HUMILITY"] == pytest.approx(0.18)

    def test_six_entries(self) -> None:
        assert len(SIGNAL_DEFAULT_WEIGHTS) == 6


@pytest.mark.unit
class TestCompositeScoreFloor:
    def test_value(self) -> None:
        assert pytest.approx(0.30) == COMPOSITE_SCORE_FLOOR

    def test_is_float(self) -> None:
        assert isinstance(COMPOSITE_SCORE_FLOOR, float)


@pytest.mark.unit
class TestPredictionErrorClassifiers:
    def test_has_three_levels(self) -> None:
        assert len(PREDICTION_ERROR_CLASSIFIERS) == 3

    def test_noise_threshold(self) -> None:
        assert PREDICTION_ERROR_CLASSIFIERS["noise"] == pytest.approx(0.10)

    def test_notable_threshold(self) -> None:
        assert PREDICTION_ERROR_CLASSIFIERS["notable"] == pytest.approx(0.40)

    def test_severe_is_inf(self) -> None:
        import math

        assert math.isinf(PREDICTION_ERROR_CLASSIFIERS["severe"])

    def test_thresholds_ordered(self) -> None:
        assert (
            PREDICTION_ERROR_CLASSIFIERS["noise"]
            < PREDICTION_ERROR_CLASSIFIERS["notable"]
            < PREDICTION_ERROR_CLASSIFIERS["severe"]
        )


@pytest.mark.unit
class TestCycleRuntime:
    def test_cycle_max_steps(self) -> None:
        assert CYCLE_MAX_STEPS == 20

    def test_recursion_depth_default(self) -> None:
        assert RECURSION_DEPTH_DEFAULT == 5

    def test_lattice_snapshot_cadence(self) -> None:
        assert LATTICE_SNAPSHOT_CADENCE == 100


@pytest.mark.unit
class TestClutchActions:
    def test_is_frozenset(self) -> None:
        assert isinstance(CLUTCH_ACTIONS, frozenset)

    def test_contains_core_actions(self) -> None:
        core = {"accept", "refine", "critique", "explore", "branch", "stop"}
        assert core.issubset(CLUTCH_ACTIONS)

    def test_contains_all_expected_actions(self) -> None:
        expected = {
            "accept",
            "refine",
            "critique",
            "explore",
            "branch",
            "retrieve_more",
            "consolidate",
            "ask_user",
            "pause",
            "stop",
        }
        assert expected == CLUTCH_ACTIONS

    def test_ten_actions(self) -> None:
        assert len(CLUTCH_ACTIONS) == 10


@pytest.mark.unit
class TestPhase6EventTypes:
    def test_is_frozenset(self) -> None:
        assert isinstance(PHASE_6_EVENT_TYPES, frozenset)

    def test_contains_session_lifecycle(self) -> None:
        assert {"SessionOpened", "CycleStarted", "CycleCompleted"}.issubset(PHASE_6_EVENT_TYPES)

    def test_contains_step_execution(self) -> None:
        assert {"StepStarted", "ContextPacketBuilt", "StepExecuted"}.issubset(PHASE_6_EVENT_TYPES)

    def test_contains_prediction_evaluation(self) -> None:
        assert {
            "PredictionMade",
            "SignalEvaluated",
            "EvaluationComposed",
            "OutcomeRecorded",
            "PredictionSevereMiss",
        }.issubset(PHASE_6_EVENT_TYPES)

    def test_contains_control_decisions(self) -> None:
        assert {
            "ClutchDecisionMade",
            "CatalystInvoked",
            "CatalystArmSelected",
        }.issubset(PHASE_6_EVENT_TYPES)

    def test_contains_leeway_gate(self) -> None:
        assert "LeewayGrantApplied" in PHASE_6_EVENT_TYPES

    def test_contains_reinjection(self) -> None:
        assert {"ContinuationBundleCreated", "ReinjectionTriggered"}.issubset(PHASE_6_EVENT_TYPES)

    def test_contains_memory_and_session_end(self) -> None:
        assert {"MemoryWriteFromCycle", "SessionFlushed"}.issubset(PHASE_6_EVENT_TYPES)

    def test_twenty_six_event_types(self) -> None:
        assert len(PHASE_6_EVENT_TYPES) == 26

    def test_matches_inspector_phase6_event_types(self) -> None:
        assert PHASE_6_EVENT_TYPES == INSPECTOR_PHASE_6_EVENT_TYPES


@pytest.mark.unit
class TestAllKnownEventTypes:
    def test_superset_of_phase6(self) -> None:
        assert PHASE_6_EVENT_TYPES.issubset(ALL_KNOWN_EVENT_TYPES)

    def test_superset_of_phase0(self) -> None:
        from cerebra.inspector.event import PHASE_0_EVENT_TYPES

        assert PHASE_0_EVENT_TYPES.issubset(ALL_KNOWN_EVENT_TYPES)

    def test_superset_of_phase5(self) -> None:
        from cerebra.inspector.event import PHASE_5_EVENT_TYPES

        assert PHASE_5_EVENT_TYPES.issubset(ALL_KNOWN_EVENT_TYPES)

    def test_superset_of_lattice(self) -> None:
        from cerebra.inspector.event import LATTICE_EVENT_TYPES

        assert LATTICE_EVENT_TYPES.issubset(ALL_KNOWN_EVENT_TYPES)
