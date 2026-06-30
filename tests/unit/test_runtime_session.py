"""Unit tests for cerebra/cognition/session.py — Phase 8 Step 1."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cerebra.cognition._constants import RECURSION_DEPTH_DEFAULT
from cerebra.cognition.session import (
    RuntimeSession,
    SessionState,
    predict_input_from_session,
)

# ── RuntimeSession ─────────────────────────────────────────────────────────────


class TestRuntimeSession:
    def _make(self, **overrides: Any) -> RuntimeSession:
        kwargs: dict[str, Any] = dict(
            session_id="sess_abc123",
            cycle_config="default",
            goal="do something",
            vault_path=Path("/tmp/vault"),
            opened_at=1_700_000_000_000,
        )
        kwargs.update(overrides)
        return RuntimeSession(**kwargs)

    def test_defaults_on_creation(self) -> None:
        s = self._make()
        assert s.state == "active"
        assert s.cycles_run == 0
        assert s.steps_run == 0
        assert s.parent_session_id is None
        assert s.recursion_depth == 0
        assert s.max_recursion_depth == RECURSION_DEPTH_DEFAULT
        assert s.flushed_at is None
        assert s.final_outcome is None

    def test_is_active_true_when_active(self) -> None:
        assert self._make(state="active").is_active is True

    def test_is_active_false_when_flushed(self) -> None:
        assert self._make(state="flushed").is_active is False

    def test_can_recurse_true_below_max(self) -> None:
        s = self._make(recursion_depth=2, max_recursion_depth=5)
        assert s.can_recurse is True

    def test_can_recurse_false_at_max(self) -> None:
        s = self._make(recursion_depth=5, max_recursion_depth=5)
        assert s.can_recurse is False

    def test_frozen_immutability(self) -> None:
        s = self._make()
        with pytest.raises(Exception):  # FrozenInstanceError
            s.state = "flushed"  # type: ignore[misc]

    def test_replace_produces_new_instance(self) -> None:
        s = self._make()
        s2 = replace(s, state="flushed", cycles_run=3)
        assert s2.state == "flushed"
        assert s2.cycles_run == 3
        assert s.state == "active"  # original unchanged

    def test_vault_path_stored_as_path(self) -> None:
        s = self._make(vault_path=Path("/tmp/my/vault"))
        assert isinstance(s.vault_path, Path)
        assert s.vault_path == Path("/tmp/my/vault")

    def test_parent_session_id_set(self) -> None:
        s = self._make(parent_session_id="sess_parent", recursion_depth=1)
        assert s.parent_session_id == "sess_parent"
        assert s.recursion_depth == 1

    def test_recursion_depth_zero_by_default(self) -> None:
        s = self._make()
        assert s.recursion_depth == 0


# ── SessionState ───────────────────────────────────────────────────────────────


class TestSessionState:
    def _make_session(self) -> RuntimeSession:
        return RuntimeSession(
            session_id="sess_abc",
            cycle_config="default",
            goal="test goal",
            vault_path=Path("/tmp/vault"),
            opened_at=1_700_000_000_000,
        )

    def test_defaults(self) -> None:
        ss = SessionState(session=self._make_session(), cycle_config_loaded={})
        assert ss.prior_step_composites == []
        assert ss.prior_step_per_signal is None

    def test_stores_session_ref(self) -> None:
        s = self._make_session()
        ss = SessionState(session=s, cycle_config_loaded={})
        assert ss.session is s

    def test_prior_step_composites_populated(self) -> None:
        ss = SessionState(
            session=self._make_session(),
            cycle_config_loaded={},
            prior_step_composites=[0.6, 0.7, 0.8],
        )
        assert ss.prior_step_composites == [0.6, 0.7, 0.8]

    def test_cycle_config_loaded_dict(self) -> None:
        ss = SessionState(
            session=self._make_session(),
            cycle_config_loaded={"temperature": 0.7, "max_steps": 10},
        )
        assert ss.cycle_config_loaded["temperature"] == 0.7

    def test_frozen_immutability(self) -> None:
        ss = SessionState(session=self._make_session(), cycle_config_loaded={})
        with pytest.raises(Exception):
            ss.prior_step_composites = [1.0]  # type: ignore[misc]


# ── predict_input_from_session ─────────────────────────────────────────────────


class TestPredictInputFromSession:
    def _make_state(
        self,
        composites: list[float] | None = None,
        per_signal: dict[str, float] | None = None,
    ) -> SessionState:
        session = RuntimeSession(
            session_id="sess_pred",
            cycle_config="default",
            goal="prediction test",
            vault_path=Path("/tmp/vault"),
            opened_at=1_700_000_000_000,
        )
        return SessionState(
            session=session,
            cycle_config_loaded={},
            prior_step_composites=composites or [],
            prior_step_per_signal=per_signal,
        )

    def test_session_id_propagated(self) -> None:
        pi = predict_input_from_session(self._make_state(), "cycle_001", "step_001")
        assert pi.session_id == "sess_pred"

    def test_cycle_and_step_id_propagated(self) -> None:
        pi = predict_input_from_session(self._make_state(), "cycle_xyz", "step_abc")
        assert pi.cycle_id == "cycle_xyz"
        assert pi.step_id == "step_abc"

    def test_empty_prior_composites(self) -> None:
        pi = predict_input_from_session(self._make_state(), "c", "s")
        assert pi.prior_step_composites == []

    def test_prior_composites_propagated(self) -> None:
        pi = predict_input_from_session(self._make_state(composites=[0.5, 0.6]), "c", "s")
        assert pi.prior_step_composites == [0.5, 0.6]

    def test_per_signal_none_step1(self) -> None:
        pi = predict_input_from_session(self._make_state(), "c", "s")
        assert pi.prior_step_per_signal is None

    def test_cycle_config_defaults_none_step1(self) -> None:
        pi = predict_input_from_session(self._make_state(), "c", "s")
        assert pi.cycle_config_defaults is None
