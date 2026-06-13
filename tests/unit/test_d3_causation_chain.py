"""Phase 8 Step 3 — D3 fix verification tests.

DEV-018: open_session() returns (RuntimeSession, bytes) tuple.
CycleRuntime uses opened_event_id as causation_id for CycleStarted,
restoring cross-stream causation from SessionOpened → CycleStarted.

Run with: pytest tests/unit/test_d3_causation_chain.py -v
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
from cerebra.cognition.llm_adapter import ClassificationResult, LLMAdapter
from cerebra.cognition.session import RuntimeSession, SessionManager
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations


class _StubLLM(LLMAdapter):
    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return "d3 stub output"

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": 0.75,
            "reasoning": "d3 stub",
        }

    def classify_d1(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


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


def _minimal_config() -> CycleConfig:
    return CycleConfig(
        name="d3.test.v0",
        version=1,
        description="",
        steps=[CycleStep("s", "", StepPromptTemplate("{{ goal }}", "free_form"))],
        max_steps=5,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("done", "all_steps_completed", {}),
        ],
        clutch_rules=[ClutchRule("accept", "", "always", "accept", {})],
    )


# ── D3: open_session returns tuple ────────────────────────────────────────────


class TestOpenSessionReturnsTuple:
    def test_open_session_returns_two_element_tuple(
        self, manager: SessionManager, vault: Path
    ) -> None:
        result = manager.open_session(
            goal="test goal",
            cycle_config="d3.test.v0",
            vault_path=vault,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_runtime_session(
        self, manager: SessionManager, vault: Path
    ) -> None:
        session, _ = manager.open_session(
            goal="test goal",
            cycle_config="d3.test.v0",
            vault_path=vault,
        )
        assert isinstance(session, RuntimeSession)

    def test_second_element_is_bytes(
        self, manager: SessionManager, vault: Path
    ) -> None:
        _, event_id = manager.open_session(
            goal="test goal",
            cycle_config="d3.test.v0",
            vault_path=vault,
        )
        assert isinstance(event_id, bytes)

    def test_event_id_is_nonempty(
        self, manager: SessionManager, vault: Path
    ) -> None:
        _, event_id = manager.open_session(
            goal="test goal",
            cycle_config="d3.test.v0",
            vault_path=vault,
        )
        assert len(event_id) > 0

    def test_different_sessions_different_event_ids(
        self, manager: SessionManager, vault: Path
    ) -> None:
        _, eid1 = manager.open_session(
            goal="goal 1", cycle_config="d3.test.v0", vault_path=vault
        )
        _, eid2 = manager.open_session(
            goal="goal 2", cycle_config="d3.test.v0", vault_path=vault
        )
        assert eid1 != eid2


# ── D3: CycleRuntime accepts and uses opened_event_id ─────────────────────────


class TestCycleRuntimeCausationChain:
    def test_cycle_runtime_accepts_opened_event_id(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session, event_id = manager.open_session(
            goal="causation test",
            cycle_config="d3.test.v0",
            vault_path=vault,
        )
        runtime = CycleRuntime(
            config=_minimal_config(),
            session=session,
            db_path=db_path,
            store=store,
            llm=_StubLLM(),
            opened_event_id=event_id,
        )
        result = runtime.run()
        assert result.cycle_id.startswith("cycle_")

    def test_cycle_runtime_accepts_none_opened_event_id(
        self, vault: Path, db_path: Path, store: FossicStore, manager: SessionManager
    ) -> None:
        session, _ = manager.open_session(
            goal="causation test no id",
            cycle_config="d3.test.v0",
            vault_path=vault,
        )
        runtime = CycleRuntime(
            config=_minimal_config(),
            session=session,
            db_path=db_path,
            store=store,
            llm=_StubLLM(),
            opened_event_id=None,
        )
        result = runtime.run()
        assert result is not None
