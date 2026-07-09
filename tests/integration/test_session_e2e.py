# SPDX-License-Identifier: Apache-2.0
"""Integration tests for Phase 8 Step 1 — session persistence + event pipeline.

Tests the full open→persist→SessionOpened event→build_session_state→PredictionInput→flush chain
against real SQLite + real FossicStore. No LLM calls.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cerebra.cognition.session import (
    RuntimeSession,
    SessionManager,
    SessionState,
    list_continuation_chain,
    list_sessions_for_vault,
    predict_input_from_session,
    read_session,
    update_session_state,
    write_session,
)
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

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
def manager(db_path: Path, store: FossicStore) -> SessionManager:
    return SessionManager(db_path=db_path, store=store)


# ── persistence helpers ───────────────────────────────────────────────────────


@pytest.mark.integration
class TestPersistenceHelpers:
    def test_write_and_read_roundtrip(self, db_path: Path, vault: Path) -> None:
        session = RuntimeSession(
            session_id="sess_rt1",
            cycle_config="default",
            goal="roundtrip goal",
            vault_path=vault,
            opened_at=1_700_000_000_000,
        )
        write_session(db_path, session)
        loaded = read_session(db_path, "sess_rt1")
        assert loaded is not None
        assert loaded.session_id == "sess_rt1"
        assert loaded.goal == "roundtrip goal"
        assert loaded.vault_path == vault
        assert loaded.state == "active"
        assert loaded.cycles_run == 0

    def test_read_nonexistent_returns_none(self, db_path: Path) -> None:
        assert read_session(db_path, "sess_missing") is None

    def test_update_session_state(self, db_path: Path, vault: Path) -> None:
        session = RuntimeSession(
            session_id="sess_upd",
            cycle_config="default",
            goal="update test",
            vault_path=vault,
            opened_at=1_700_000_000_000,
        )
        write_session(db_path, session)
        updated = replace(
            session,
            state="flushed",
            flushed_at=1_700_000_001_000,
            final_outcome="completed",
            cycles_run=3,
            steps_run=12,
        )
        update_session_state(db_path, updated)
        loaded = read_session(db_path, "sess_upd")
        assert loaded is not None
        assert loaded.state == "flushed"
        assert loaded.cycles_run == 3
        assert loaded.steps_run == 12
        assert loaded.final_outcome == "completed"

    def test_list_sessions_for_vault_empty(self, db_path: Path, vault: Path) -> None:
        assert list_sessions_for_vault(db_path, vault) == []

    def test_list_sessions_for_vault_returns_all(self, db_path: Path, vault: Path) -> None:
        for i in range(3):
            write_session(
                db_path,
                RuntimeSession(
                    session_id=f"sess_{i}",
                    cycle_config="default",
                    goal=f"goal {i}",
                    vault_path=vault,
                    opened_at=1_700_000_000_000 + i * 1000,
                ),
            )
        sessions = list_sessions_for_vault(db_path, vault)
        assert len(sessions) == 3
        assert [s.session_id for s in sessions] == ["sess_0", "sess_1", "sess_2"]

    def test_list_sessions_for_vault_filtered_by_state(self, db_path: Path, vault: Path) -> None:
        for i in range(3):
            s = RuntimeSession(
                session_id=f"sess_f{i}",
                cycle_config="default",
                goal="g",
                vault_path=vault,
                opened_at=1_700_000_000_000 + i * 1000,
            )
            write_session(db_path, s)

        # flush the first one
        loaded = read_session(db_path, "sess_f0")
        assert loaded is not None
        update_session_state(db_path, replace(loaded, state="flushed", flushed_at=1700000099000))

        active = list_sessions_for_vault(db_path, vault, state="active")
        assert len(active) == 2
        flushed = list_sessions_for_vault(db_path, vault, state="flushed")
        assert len(flushed) == 1

    def test_list_continuation_chain_single(self, db_path: Path, vault: Path) -> None:
        write_session(
            db_path,
            RuntimeSession(
                session_id="sess_root",
                cycle_config="default",
                goal="root",
                vault_path=vault,
                opened_at=1_700_000_000_000,
            ),
        )
        chain = list_continuation_chain(db_path, "sess_root")
        assert len(chain) == 1
        assert chain[0].session_id == "sess_root"

    def test_list_continuation_chain_three_deep(self, db_path: Path, vault: Path) -> None:
        for i, (sid, parent) in enumerate(
            [
                ("sess_r", None),
                ("sess_c1", "sess_r"),
                ("sess_c2", "sess_c1"),
            ]
        ):
            write_session(
                db_path,
                RuntimeSession(
                    session_id=sid,
                    cycle_config="default",
                    goal="g",
                    vault_path=vault,
                    opened_at=1_700_000_000_000 + i * 1000,
                    parent_session_id=parent,
                    recursion_depth=i,
                ),
            )
        chain = list_continuation_chain(db_path, "sess_r")
        assert [s.session_id for s in chain] == ["sess_r", "sess_c1", "sess_c2"]


# ── SessionManager lifecycle ──────────────────────────────────────────────────


@pytest.mark.integration
class TestSessionManagerLifecycle:
    def test_open_session_returns_active_session(
        self, manager: SessionManager, vault: Path
    ) -> None:
        s, _ = manager.open_session(goal="test goal", cycle_config="default", vault_path=vault)
        assert s.state == "active"
        assert s.goal == "test goal"
        assert s.vault_path == vault
        assert s.recursion_depth == 0
        assert s.parent_session_id is None

    def test_open_session_persisted(
        self, manager: SessionManager, vault: Path, db_path: Path
    ) -> None:
        s, _ = manager.open_session(goal="persist check", cycle_config="default", vault_path=vault)
        loaded = read_session(db_path, s.session_id)
        assert loaded is not None
        assert loaded.session_id == s.session_id
        assert loaded.goal == "persist check"

    def test_open_session_emits_session_opened_event(
        self, manager: SessionManager, vault: Path, store: FossicStore
    ) -> None:
        from fossic import ReadQuery

        s, _ = manager.open_session(goal="emit check", cycle_config="default", vault_path=vault)
        events = store._store.read_range(ReadQuery(stream_id=f"cerebra/agent-trace/{s.session_id}"))
        opened_events = [e for e in events if e.event_type == "SessionOpened"]
        assert len(opened_events) == 1

        payload = opened_events[0].payload()
        assert payload["session_id"] == s.session_id
        assert payload["goal"] == "emit check"
        assert payload["recursion_depth"] == 0

    def test_session_opened_stream_uses_session_id_as_cycle_id(
        self, manager: SessionManager, vault: Path, store: FossicStore
    ) -> None:
        """DEV-012: session_id IS the cycle_id segment — no 'session-' prefix."""
        from fossic import ReadQuery

        s, _ = manager.open_session(goal="stream check", cycle_config="default", vault_path=vault)
        events = store._store.read_range(ReadQuery(stream_id=f"cerebra/agent-trace/{s.session_id}"))
        assert len(events) > 0, "No events on expected stream"
        # Verify no events on a 'session-<id>' prefixed stream
        wrong_stream = store._store.read_range(
            ReadQuery(stream_id=f"cerebra/agent-trace/session-{s.session_id}")
        )
        assert len(wrong_stream) == 0, "Events incorrectly on session-prefixed stream"

    def test_flush_session_marks_flushed(self, manager: SessionManager, vault: Path) -> None:
        s, _ = manager.open_session(goal="flush test", cycle_config="default", vault_path=vault)
        flushed = manager.flush_session(
            session_id=s.session_id,
            outcome="completed",
            total_cycles=3,
            total_steps=9,
        )
        assert flushed.state == "flushed"
        assert flushed.final_outcome == "completed"
        assert flushed.cycles_run == 3
        assert flushed.steps_run == 9
        assert flushed.flushed_at is not None

    def test_flush_session_updates_persisted_state(
        self, manager: SessionManager, vault: Path, db_path: Path
    ) -> None:
        s, _ = manager.open_session(goal="flush persist", cycle_config="default", vault_path=vault)
        manager.flush_session(
            session_id=s.session_id, outcome="done", total_cycles=1, total_steps=3
        )
        loaded = read_session(db_path, s.session_id)
        assert loaded is not None
        assert loaded.state == "flushed"
        assert loaded.final_outcome == "done"

    def test_flush_nonexistent_raises(self, manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="Session not found"):
            manager.flush_session("sess_missing", "done", 0, 0)

    def test_flush_already_flushed_raises(self, manager: SessionManager, vault: Path) -> None:
        s, _ = manager.open_session(goal="double flush", cycle_config="default", vault_path=vault)
        manager.flush_session(
            session_id=s.session_id, outcome="done", total_cycles=0, total_steps=0
        )
        with pytest.raises(ValueError, match="not active"):
            manager.flush_session(
                session_id=s.session_id, outcome="done", total_cycles=0, total_steps=0
            )

    def test_open_child_session_increments_depth(
        self, manager: SessionManager, vault: Path
    ) -> None:
        parent, _ = manager.open_session(goal="parent", cycle_config="default", vault_path=vault)
        child, _ = manager.open_session(
            goal="child",
            cycle_config="default",
            vault_path=vault,
            parent_session_id=parent.session_id,
        )
        assert child.recursion_depth == 1
        assert child.parent_session_id == parent.session_id

    def test_open_child_max_recursion_raises(
        self, manager: SessionManager, vault: Path, db_path: Path
    ) -> None:
        s = RuntimeSession(
            session_id="sess_maxdepth",
            cycle_config="default",
            goal="at limit",
            vault_path=vault,
            opened_at=1_700_000_000_000,
            recursion_depth=5,
            max_recursion_depth=5,
        )
        write_session(db_path, s)
        with pytest.raises(ValueError, match="max recursion depth"):
            manager.open_session(
                goal="too deep",
                cycle_config="default",
                vault_path=vault,
                parent_session_id="sess_maxdepth",
            )

    def test_build_session_state_returns_state(self, manager: SessionManager, vault: Path) -> None:
        s, _ = manager.open_session(goal="state build", cycle_config="default", vault_path=vault)
        ss = manager.build_session_state(s.session_id)
        assert isinstance(ss, SessionState)
        assert ss.session.session_id == s.session_id
        assert isinstance(ss.cycle_config_loaded, dict)
        assert ss.prior_step_composites == []

    def test_build_session_state_nonexistent_raises(self, manager: SessionManager) -> None:
        with pytest.raises(ValueError, match="Session not found"):
            manager.build_session_state("sess_missing")


# ── PredictionInput adapter integration ───────────────────────────────────────


@pytest.mark.integration
class TestPredictInputFromSessionIntegration:
    def test_full_open_to_prediction_input(self, manager: SessionManager, vault: Path) -> None:
        s, _ = manager.open_session(goal="predict test", cycle_config="default", vault_path=vault)
        ss = manager.build_session_state(s.session_id)
        pi = predict_input_from_session(ss, cycle_id="cycle_001", step_id="step_001")
        assert pi.session_id == s.session_id
        assert pi.cycle_id == "cycle_001"
        assert pi.step_id == "step_001"
        assert pi.prior_step_composites == []
        assert pi.prior_step_per_signal is None
        assert pi.cycle_config_defaults is None

    def test_prediction_input_session_id_matches_opened(
        self, manager: SessionManager, vault: Path
    ) -> None:
        s, _ = manager.open_session(goal="id check", cycle_config="default", vault_path=vault)
        ss = manager.build_session_state(s.session_id)
        pi = predict_input_from_session(ss, "c", "s")
        assert pi.session_id == s.session_id
