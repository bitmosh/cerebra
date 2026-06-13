"""Unit tests for cerebra.cognition.cycle_runtime — Phase 8 Step 2.

Uses a real migrated SQLite DB + real FossicStore, but stubs out:
  - LLMAdapter.complete() and complete_structured() for deterministic output
  - (Retrieval pipeline uses real DB but with no data → abstained packets)
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
from cerebra.cognition.cycle_runtime import CycleResult, CycleRuntime, StepResult
from cerebra.cognition.llm_adapter import ClassificationError, ClassificationResult, LLMAdapter
from cerebra.cognition.session import RuntimeSession
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations


# ── Stub LLM adapters ─────────────────────────────────────────────────────────


class _StubLLM(LLMAdapter):
    """Returns fixed text from complete() and a fixed score from complete_structured()."""

    def __init__(self, text: str = "stub output", score: float = 0.75) -> None:
        self._text = text
        self._score = score

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return self._text

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": self._score,
            "reasoning": "stub",
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
    """Always raises ClassificationError from complete()."""

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        raise ClassificationError("stub failure")


class _FailOnceLLM(_StubLLM):
    """Fails on first complete() call; succeeds on second."""

    def __init__(self, text: str = "recovered output") -> None:
        super().__init__(text=text)
        self._calls = 0

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self._calls += 1
        if self._calls == 1:
            raise ClassificationError("first attempt failure")
        return self._text


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


def _make_session(vault: Path) -> RuntimeSession:
    return RuntimeSession(
        session_id="sess_test001",
        cycle_config="test.v0",
        goal="test goal for unit",
        vault_path=vault,
        opened_at=1_700_000_000_000,
    )


def _two_step_config() -> CycleConfig:
    """Minimal 2-step cycle config with always-accept clutch rule."""
    return CycleConfig(
        name="test.two_step.v0",
        version=1,
        description="",
        steps=[
            CycleStep("step_a", "", StepPromptTemplate("{{ goal }}", "free_form")),
            CycleStep("step_b", "", StepPromptTemplate("{{ prior_step_output }}", "free_form")),
        ],
        max_steps=5,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("done", "all_steps_completed", {}),
        ],
        clutch_rules=[
            ClutchRule("default", "", "always", "accept", {}),
        ],
    )


def _one_step_stop_config() -> CycleConfig:
    """1-step config that always triggers stop on the first clutch decision."""
    return CycleConfig(
        name="test.stop.v0",
        version=1,
        description="",
        steps=[
            CycleStep("step_a", "", StepPromptTemplate("{{ goal }}", "free_form")),
        ],
        max_steps=5,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
            StopCondition("xstop", "explicit_clutch_stop", {}),
        ],
        clutch_rules=[
            ClutchRule("always_stop", "", "always", "stop", {}),
        ],
    )


def _cap_config() -> CycleConfig:
    """3-step config with max_steps=1 so cap fires immediately after step 1."""
    return CycleConfig(
        name="test.cap.v0",
        version=1,
        description="",
        steps=[
            CycleStep("step_a", "", StepPromptTemplate("{{ goal }}", "free_form")),
            CycleStep("step_b", "", StepPromptTemplate("{{ goal }}", "free_form")),
            CycleStep("step_c", "", StepPromptTemplate("{{ goal }}", "free_form")),
        ],
        max_steps=1,
        stop_conditions=[
            StopCondition("cap", "max_steps_reached", {}),
        ],
        clutch_rules=[
            ClutchRule("default", "", "always", "accept", {}),
        ],
    )


# ── StepResult / CycleResult dataclass tests ──────────────────────────────────


class TestDataclasses:
    def test_step_result_defaults(self) -> None:
        sr = StepResult(
            step_id="step_001",
            step_name="step_a",
            step_index=0,
            output_text="hello",
            composite_score=0.7,
            clutch_action="accept",
        )
        assert not sr.failed
        assert sr.error_message is None

    def test_step_result_failed(self) -> None:
        sr = StepResult(
            step_id="step_002",
            step_name="step_a",
            step_index=0,
            output_text="",
            composite_score=0.0,
            clutch_action="stop",
            failed=True,
            error_message="timeout",
        )
        assert sr.failed
        assert sr.error_message == "timeout"

    def test_cycle_result_fields(self) -> None:
        cr = CycleResult(
            cycle_id="cycle_abc",
            session_id="sess_001",
            total_steps=3,
            outcome="accept",
            final_output="result text",
        )
        assert cr.cycle_id == "cycle_abc"
        assert cr.outcome == "accept"
        assert cr.step_results == []


# ── CycleRuntime._call_llm_with_retry (unit-level) ────────────────────────────


class TestCallLlmWithRetry:
    """Test the retry helper in isolation using a real but minimal runtime."""

    def _make_runtime(self, vault: Path, db_path: Path, store: FossicStore, llm: LLMAdapter) -> CycleRuntime:
        return CycleRuntime(
            config=_two_step_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=llm,
        )

    def _make_emitter(self, store: FossicStore) -> Any:
        from cerebra.cognition.event_emitter import EventEmitter
        return EventEmitter(store, "sess_t001", "cycle_t001")

    def test_success_returns_output_no_fail(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = self._make_runtime(vault, db_path, store, _StubLLM("hello world"))
        emitter = self._make_emitter(store)
        # Emit a dummy event to get a valid bytes ID
        dummy_id = emitter.emit_cycle_event("CycleStarted", {"x": 1})
        output, failed, err = runtime._call_llm_with_retry(
            "prompt", "sess_t001", "cycle_t001", "step_t001", emitter, dummy_id
        )
        assert output == "hello world"
        assert not failed
        assert err is None

    def test_fail_twice_returns_empty_failed_true(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = self._make_runtime(vault, db_path, store, _FailingLLM())
        emitter = self._make_emitter(store)
        dummy_id = emitter.emit_cycle_event("CycleStarted", {"x": 1})
        output, failed, err = runtime._call_llm_with_retry(
            "prompt", "sess_t001", "cycle_t001", "step_t001", emitter, dummy_id
        )
        assert output == ""
        assert failed
        assert err is not None
        assert "stub failure" in err

    def test_fail_once_recovers(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = self._make_runtime(vault, db_path, store, _FailOnceLLM("recovered"))
        emitter = self._make_emitter(store)
        dummy_id = emitter.emit_cycle_event("CycleStarted", {"x": 1})
        output, failed, err = runtime._call_llm_with_retry(
            "prompt", "sess_t001", "cycle_t001", "step_t001", emitter, dummy_id
        )
        assert output == "recovered"
        assert not failed
        assert err is None


# ── CycleRuntime.run() integration-style unit tests ───────────────────────────


@pytest.mark.integration
class TestCycleRuntimeRun:
    def test_run_returns_cycle_result(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = CycleRuntime(
            config=_two_step_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=_StubLLM(score=0.75),
        )
        result = runtime.run()
        assert isinstance(result, CycleResult)
        assert result.cycle_id.startswith("cycle_")
        assert result.session_id == "sess_test001"

    def test_run_all_steps_complete_outcome_accept(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = CycleRuntime(
            config=_two_step_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=_StubLLM(text="step output", score=0.75),
        )
        result = runtime.run()
        assert result.outcome == "accept"
        assert result.total_steps == 2
        assert result.final_output == "step output"

    def test_run_clutch_stop_outcome_stop(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = CycleRuntime(
            config=_one_step_stop_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=_StubLLM(score=0.75),
        )
        result = runtime.run()
        assert result.outcome == "stop"

    def test_run_cap_reached(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        # max_steps=1, 3 steps in config → cap fires after 1 step
        runtime = CycleRuntime(
            config=_cap_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=_StubLLM(score=0.75),
        )
        result = runtime.run()
        assert result.outcome == "cap_reached"
        assert result.total_steps == 1

    def test_run_step_results_populated(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        runtime = CycleRuntime(
            config=_two_step_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=_StubLLM(text="my output", score=0.75),
        )
        result = runtime.run()
        assert len(result.step_results) == 2
        sr = result.step_results[0]
        assert isinstance(sr, StepResult)
        assert sr.step_name == "step_a"
        assert sr.output_text == "my output"
        assert sr.clutch_action == "accept"
        assert not sr.failed

    def test_run_llm_failure_marks_step_failed(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        # With a failing LLM and a "stop on fail" clutch, check step failed=True
        runtime = CycleRuntime(
            config=_one_step_stop_config(),
            session=_make_session(vault),
            db_path=db_path,
            store=store,
            llm=_FailingLLM(),
        )
        result = runtime.run()
        assert result.outcome == "stop"
        assert len(result.step_results) == 1
        sr = result.step_results[0]
        assert sr.failed is True
        assert sr.composite_score == 0.0
        assert "stub failure" in (sr.error_message or "")

    def test_run_cycle_id_unique_per_call(self, vault: Path, db_path: Path, store: FossicStore) -> None:
        cfg = _two_step_config()
        sess = _make_session(vault)
        r1 = CycleRuntime(cfg, sess, db_path, store, _StubLLM()).run()
        r2 = CycleRuntime(cfg, sess, db_path, store, _StubLLM()).run()
        assert r1.cycle_id != r2.cycle_id
