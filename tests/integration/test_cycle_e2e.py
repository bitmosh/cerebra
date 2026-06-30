"""Phase 8 Step 2 end-to-end integration tests — CycleRuntime full execution.

Runs the full CycleRuntime cycle against a real migrated temp vault.
No LLM calls: uses _StubLLM / _FailingLLM adapters for deterministic output.
No dev-vault dependency.

Run with: pytest tests/integration/test_cycle_e2e.py -m integration -v
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
from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult, LLMAdapter
from cerebra.cognition.session import RuntimeSession, SessionManager
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

# ── Stub LLM adapters ─────────────────────────────────────────────────────────


class _StubLLM(LLMAdapter):
    def __init__(self, text: str = "e2e output", score: float = 0.75) -> None:
        self._text = text
        self._score = score

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._text

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": self._score,
            "reasoning": "e2e stub",
        }

    def classify_d1(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


class _FailingLLM(_StubLLM):
    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        raise ClassificationError("e2e LLM failure")


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


def _open_session(
    manager: SessionManager, vault: Path, cycle_config: str = "simple.planning.v0"
) -> RuntimeSession:
    session, _event_id = manager.open_session(
        goal="design a search feature",
        cycle_config=cycle_config,
        vault_path=vault,
    )
    return session


def _minimal_accept_config() -> CycleConfig:
    """Single-step config — simplest possible acceptance path."""
    return CycleConfig(
        name="e2e.minimal.v0",
        version=1,
        description="",
        steps=[
            CycleStep("the_only_step", "", StepPromptTemplate("{{ goal }}", "free_form")),
        ],
        max_steps=3,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("done", "all_steps_completed", {}),
        ],
        clutch_rules=[
            ClutchRule("default", "", "always", "accept", {}),
        ],
    )


# ── CycleResult shape and basic fields ───────────────────────────────────────


@pytest.mark.integration
class TestCycleResultFields:
    def test_result_has_cycle_id(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        assert result.cycle_id.startswith("cycle_")

    def test_result_session_id_matches(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        assert result.session_id == session.session_id

    def test_minimal_accept_outcome(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        assert result.outcome == "accept"
        assert result.total_steps == 1
        assert result.final_output == "e2e output"

    def test_step_result_correct(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(
            _minimal_accept_config(), session, db_path, store, _StubLLM(text="the answer")
        )
        result = runtime.run()
        assert len(result.step_results) == 1
        sr = result.step_results[0]
        assert sr.step_name == "the_only_step"
        assert sr.output_text == "the answer"
        assert not sr.failed


# ── Fossic event emission checks ──────────────────────────────────────────────


@pytest.mark.integration
class TestFossicEvents:
    def _read_cycle_events(self, store: FossicStore, session_id: str) -> list[Any]:
        from fossic import ReadQuery

        return store._store.read_range(ReadQuery(stream_id=f"cerebra/agent-trace/{session_id}"))

    def _event_types(self, events: list[Any]) -> list[str]:
        return [e.event_type for e in events]

    def test_cycle_started_emitted(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "CycleStarted" in types

    def test_step_started_emitted(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "StepStarted" in types

    def test_step_executed_emitted_on_success(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "StepExecuted" in types

    def test_clutch_decision_emitted(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "ClutchDecisionMade" in types

    def test_memory_write_emitted_on_accept(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "LeewayGrantApplied" in types
        assert "MemoryWriteFromCycle" in types

    def test_cycle_completed_emitted(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "CycleCompleted" in types

    def test_session_flushed_emitted(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "SessionFlushed" in types

    def test_step_execution_failed_emitted_on_double_fail(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        stop_on_fail_cfg = CycleConfig(
            name="e2e.fail.v0",
            version=1,
            description="",
            steps=[CycleStep("fail_step", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=3,
            stop_conditions=[
                StopCondition("cap", "max_steps_reached", {}),
                StopCondition("xstop", "explicit_clutch_stop", {}),
            ],
            clutch_rules=[ClutchRule("always_stop", "", "always", "stop", {})],
        )
        session = _open_session(manager, vault, "e2e.fail.v0")
        runtime = CycleRuntime(stop_on_fail_cfg, session, db_path, store, _FailingLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "StepExecutionFailed" in types

    def test_context_packet_built_emitted(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert "ContextPacketBuilt" in types

    def test_event_ordering_cycle_start_before_step(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        # Stream now includes SessionOpened (before CycleStarted); test the
        # meaningful invariant: CycleStarted precedes the first StepStarted.
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert types.index("CycleStarted") < types.index("StepStarted")

    def test_event_ordering_completed_before_flushed(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()
        types = self._event_types(self._read_cycle_events(store, result.session_id))
        assert types.index("CycleCompleted") < types.index("SessionFlushed")


# ── Outcome variants ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestOutcomeVariants:
    def test_stop_outcome_from_clutch(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        stop_cfg = CycleConfig(
            name="e2e.stop.v0",
            version=1,
            description="",
            steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
            max_steps=5,
            stop_conditions=[
                StopCondition("cap", "max_steps_reached", {}),
                StopCondition("xstop", "explicit_clutch_stop", {}),
            ],
            clutch_rules=[ClutchRule("stop_always", "", "always", "stop", {})],
        )
        session = _open_session(manager, vault, "e2e.stop.v0")
        runtime = CycleRuntime(stop_cfg, session, db_path, store, _StubLLM())
        result = runtime.run()
        assert result.outcome == "stop"

    def test_cap_reached_outcome(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        cap_cfg = CycleConfig(
            name="e2e.cap.v0",
            version=1,
            description="",
            steps=[
                CycleStep("s1", "", StepPromptTemplate("{{ goal }}", "free_form")),
                CycleStep("s2", "", StepPromptTemplate("{{ goal }}", "free_form")),
            ],
            max_steps=1,
            stop_conditions=[StopCondition("cap", "max_steps_reached", {})],
            clutch_rules=[ClutchRule("d", "", "always", "accept", {})],
        )
        session = _open_session(manager, vault, "e2e.cap.v0")
        runtime = CycleRuntime(cap_cfg, session, db_path, store, _StubLLM())
        result = runtime.run()
        assert result.outcome == "cap_reached"


# ── Session flush integration ─────────────────────────────────────────────────


@pytest.mark.integration
class TestSessionFlushIntegration:
    def test_run_then_flush_session(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        """CycleRuntime.run() completes; SessionManager.flush_session() succeeds."""
        session = _open_session(manager, vault, "e2e.minimal.v0")
        runtime = CycleRuntime(_minimal_accept_config(), session, db_path, store, _StubLLM())
        result = runtime.run()

        flushed = manager.flush_session(
            session_id=session.session_id,
            outcome="accepted",
            total_cycles=1,
            total_steps=result.total_steps,
        )
        assert flushed.state == "flushed"
        assert flushed.final_outcome == "accepted"
        assert flushed.steps_run == result.total_steps
