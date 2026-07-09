# SPDX-License-Identifier: Apache-2.0
"""Phase 8 v0.3.5a integration tests — D1 closure: episode persistence.

Verifies that CycleRuntime.run() on accept writes real episode records to
cycle_episode_records (not just synthetic stub IDs).

Run with: pytest tests/unit/test_cycle_d1_closure.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cerebra.cognition.cycle_config import (
    ClutchRule,
    CycleConfig,
    CycleStep,
    StepPromptTemplate,
    StopCondition,
)
from cerebra.cognition.cycle_runtime import CycleRuntime
from cerebra.cognition.episode_writer import EpisodeWriter
from cerebra.cognition.llm_adapter import ClassificationResult, LLMAdapter
from cerebra.cognition.session import RuntimeSession, SessionManager
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

# ── Stub LLM ─────────────────────────────────────────────────────────────────


class _StubLLM(LLMAdapter):
    def __init__(self, text: str = "d1 test output", score: float = 0.75) -> None:
        self._text = text
        self._score = score

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._text

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": self._score,
            "reasoning": "d1 stub",
        }

    def classify_d1(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    db_path = tmp_path / "data" / "cerebra.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(db_path)
    return tmp_path


@pytest.fixture()
def db_path(vault: Path) -> Path:
    return vault / "data" / "cerebra.db"


@pytest.fixture()
def store(vault: Path) -> FossicStore:
    return FossicStore(vault)


@pytest.fixture()
def manager(db_path: Path, store: FossicStore) -> SessionManager:
    return SessionManager(db_path=db_path, store=store)


@pytest.fixture()
def writer(db_path: Path) -> EpisodeWriter:
    return EpisodeWriter(db_path)


def _open_session(
    manager: SessionManager, vault: Path, cycle_config: str = "d1.test.v0"
) -> tuple[RuntimeSession, bytes]:
    return manager.open_session(
        goal="design a caching layer",
        cycle_config=cycle_config,
        vault_path=vault,
    )


def _minimal_accept_config() -> CycleConfig:
    return CycleConfig(
        name="d1.test.v0",
        version=1,
        description="",
        steps=[
            CycleStep("plan", "", StepPromptTemplate("{{ goal }}", "free_form")),
        ],
        max_steps=3,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("done", "all_steps_completed", {}),
        ],
        clutch_rules=[ClutchRule("accept", "", "always", "accept", {})],
    )


def _two_step_config() -> CycleConfig:
    return CycleConfig(
        name="d1.twostep.v0",
        version=1,
        description="",
        steps=[
            CycleStep("plan", "", StepPromptTemplate("{{ goal }}", "free_form")),
            CycleStep("evaluate", "", StepPromptTemplate("{{ goal }}", "free_form")),
        ],
        max_steps=5,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("done", "all_steps_completed", {}),
        ],
        clutch_rules=[ClutchRule("accept", "", "always", "accept", {})],
    )


# ── Episode persistence on accept ─────────────────────────────────────────────


class TestEpisodePersistenceOnAccept:
    def test_accept_cycle_writes_episode(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        result = runtime.run()
        assert result.outcome == "accept"
        episodes = writer.list_for_runtime_session(session.session_id)
        assert len(episodes) == 1

    def test_episode_content_matches_llm_output(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(text="specific output text"),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].content == "specific output text"

    def test_episode_runtime_session_id_matches(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].runtime_session_id == session.session_id

    def test_episode_step_name_matches(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].step_name == "plan"

    def test_two_step_accept_writes_two_episodes(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault, "d1.twostep.v0")
        runtime = CycleRuntime(
            _two_step_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        result = runtime.run()
        assert result.outcome == "accept"
        episodes = writer.list_for_runtime_session(session.session_id)
        assert len(episodes) == 2

    def test_two_step_episode_step_names(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault, "d1.twostep.v0")
        runtime = CycleRuntime(
            _two_step_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        names = {ep.step_name for ep in episodes}
        assert names == {"plan", "evaluate"}

    def test_stop_outcome_writes_no_episodes(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        stop_cfg = CycleConfig(
            name="d1.stop.v0",
            version=1,
            description="",
            steps=[CycleStep("plan", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=5,
            stop_conditions=[
                StopCondition("cap", "max_steps_reached", {}),
                StopCondition("xstop", "explicit_clutch_stop", {}),
            ],
            clutch_rules=[ClutchRule("stop_always", "", "always", "stop", {})],
        )
        session, eid = _open_session(manager, vault, "d1.stop.v0")
        runtime = CycleRuntime(
            stop_cfg,
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        result = runtime.run()
        assert result.outcome == "stop"
        assert writer.list_for_runtime_session(session.session_id) == []

    def test_episode_metadata_has_step_index(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].metadata is not None
        assert "step_index" in episodes[0].metadata

    def test_episode_metadata_has_step_executions_count(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].metadata is not None
        assert "step_executions_count" in episodes[0].metadata

    def test_no_wm_session_episode_still_persists(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        """Episodes persist even without an active working memory session (nullable FK)."""
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert len(episodes) == 1
        # No WM session was created, so working_memory_session_id should be None
        assert episodes[0].working_memory_session_id is None


# ── MemoryWriteFromCycle event has real record_id ─────────────────────────────


class TestMemoryWriteFromCycleEvent:
    def _read_events(self, store: FossicStore, session_id: str) -> list[Any]:
        from fossic import ReadQuery

        return store._store.read_range(ReadQuery(stream_id=f"cerebra/agent-trace/{session_id}"))

    def test_memory_write_event_record_id_starts_with_ep(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        events = self._read_events(store, session.session_id)
        mw_events = [e for e in events if e.event_type == "MemoryWriteFromCycle"]
        assert len(mw_events) == 1
        payload = mw_events[0].payload()
        assert payload["record_id"].startswith("ep_")

    def test_memory_write_event_record_id_in_db(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        """The record_id in the event must exist in cycle_episode_records (no more stub)."""
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        events = self._read_events(store, session.session_id)
        mw_events = [e for e in events if e.event_type == "MemoryWriteFromCycle"]
        payload = mw_events[0].payload()
        record_id = payload["record_id"]
        loaded = writer.read(record_id)
        assert loaded is not None, f"record_id {record_id!r} not in cycle_episode_records"

    def test_memory_write_event_table_target_field(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        events = self._read_events(store, session.session_id)
        mw_events = [e for e in events if e.event_type == "MemoryWriteFromCycle"]
        payload = mw_events[0].payload()
        assert payload["table_target"] == "cycle_episode_records"


# ── Citation extraction ───────────────────────────────────────────────────────


class TestCitationExtraction:
    def test_extract_citations_finds_rec_ids(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(text="Based on rec_aabbccddeeff, the answer is yes."),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].cited_record_ids == ["rec_aabbccddeeff"]

    def test_extract_citations_empty_for_no_pattern(
        self,
        vault: Path,
        db_path: Path,
        store: FossicStore,
        manager: SessionManager,
        writer: EpisodeWriter,
    ) -> None:
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(text="No citations in this output."),
            opened_event_id=eid,
            episode_writer=writer,
        )
        runtime.run()
        episodes = writer.list_for_runtime_session(session.session_id)
        assert episodes[0].cited_record_ids == []


# ── EpisodeWriter injected default ───────────────────────────────────────────


class TestEpisodeWriterDefaultInjection:
    def test_runtime_auto_constructs_episode_writer(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        """CycleRuntime auto-constructs EpisodeWriter if not injected."""
        session, eid = _open_session(manager, vault)
        runtime = CycleRuntime(
            _minimal_accept_config(),
            session,
            db_path,
            store,
            _StubLLM(),
            opened_event_id=eid,
            # No episode_writer passed
        )
        result = runtime.run()
        assert result.outcome == "accept"
        # Verify episode was persisted via the auto-constructed writer
        auto_writer = EpisodeWriter(db_path)
        episodes = auto_writer.list_for_runtime_session(session.session_id)
        assert len(episodes) == 1
