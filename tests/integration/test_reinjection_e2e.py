"""Integration tests — re-injection trigger and child session spawn (Phase 9 Step 4).

Tests the full continuation path:
  Cycle hits cap_reached with no accepted step → ReinjectionTriggerEvaluator fires
  → BundleDistiller distils context → child session spawned → child cycle runs
  → chain terminates at max_recursion_depth.

Uses _StubLLM (same pattern as test_catalyst_e2e.py) and a minimal in-memory
cycle config with max_steps=2 so cycles terminate quickly.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from cerebra.cognition.continuation_bundle import list_bundles_for_session
from cerebra.cognition.cycle_config import (
    CycleConfig,
    _parse_config,
)
from cerebra.cognition.cycle_runtime import CycleResult, CycleRuntime
from cerebra.cognition.llm_adapter import ClassificationResult, LLMAdapter
from cerebra.cognition.session import SessionManager, read_session
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

# ── Stub LLM ──────────────────────────────────────────────────────────────────


class _StubLLM(LLMAdapter):
    """Deterministic stub that always returns low composite — never triggers accept."""

    def __init__(self, score: float = 0.55) -> None:
        self._score = score

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return "Stub output for reinjection test."

    def complete_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "checks": [{"item": i, "severity": 0, "specific_lines": ""} for i in range(1, 6)],
            "overall_score": self._score,
            "reasoning": "reinjection e2e stub",
        }

    def classify_d1(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_quadrant(self, content: str) -> ClassificationResult:
        raise NotImplementedError

    def classify_within_quadrant(self, content: str, quadrant: str) -> ClassificationResult:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


# ── Config factory ────────────────────────────────────────────────────────────


def _make_reinjection_config(max_recursion_depth: int = 2) -> CycleConfig:
    """Minimal cycle config that always hits cap_reached (no accept path with score 0.55)."""
    data: dict[str, Any] = {
        "name": "test_reinjection",
        "version": 1,
        "description": "Minimal test config for re-injection",
        "max_steps": 2,
        "composite_floor": 0.3,
        "max_recursion_depth": max_recursion_depth,
        "steps": [
            {
                "name": "plan",
                "description": "Plan step",
                "prompt_template": {
                    "template": "Goal: {{ goal }}\n\nCreate a plan.",
                    "expected_output_format": "free_form",
                },
            }
        ],
        "stop_conditions": [
            {"name": "max_steps_hit", "type": "max_steps_reached", "parameters": {}},
        ],
        "clutch_rules": [
            # accept only on very high composite (never fires with score 0.55)
            {
                "name": "accept_high",
                "description": "Accept only on very high quality",
                "predicate_name": "composite_above_threshold",
                "action": "accept",
                "parameters": {"threshold": 0.95},
            },
            # always refine otherwise — keeps cycle on same step until max_steps
            {
                "name": "refine_always",
                "description": "Always refine if not accepted",
                "predicate_name": "always",
                "action": "refine",
                "parameters": {},
            },
        ],
        "reinjection_triggers": [
            {
                "name": "continue_on_max_steps",
                "predicate": "max_steps_without_acceptance",
                "parameters": {},
            }
        ],
    }
    return _parse_config(data)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_vault() -> tuple[Path, Path]:
    tmp = tempfile.mkdtemp()
    vault = Path(tmp)
    db = vault / "data" / "cerebra.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(db)
    return vault, db


def _run_reinjection_cycle(
    max_recursion_depth: int = 2,
    score: float = 0.55,
) -> tuple[CycleResult, Path, Path]:
    """Run a minimal cycle that hits cap_reached and triggers re-injection."""
    vault_path, db_path = _make_vault()
    config = _make_reinjection_config(max_recursion_depth=max_recursion_depth)
    store = FossicStore(vault_path)
    manager = SessionManager(db_path=db_path, store=store)
    session, opened_event_id = manager.open_session(
        vault_path=vault_path,
        goal="Build a feature.",
        cycle_config=config.name,
    )
    runtime = CycleRuntime(config, session, db_path, store, _StubLLM(score=score), opened_event_id)
    result = runtime.run()
    return result, vault_path, db_path


def _chain_length(result: CycleResult) -> int:
    """Count the depth of the result chain (1 = just parent, 2 = parent + child, …)."""
    depth = 1
    cur = result
    while cur.child_result is not None:
        depth += 1
        cur = cur.child_result
    return depth


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestReinjectionTrigger:

    def test_parent_cycle_hits_cap_reached(self) -> None:
        result, _, _ = _run_reinjection_cycle()
        assert result.outcome == "cap_reached"

    def test_reinjection_fires_and_child_result_present(self) -> None:
        result, _, _ = _run_reinjection_cycle(max_recursion_depth=1)
        # max_recursion_depth=1: depth 0 can spawn (0 < 1), depth 1 blocked (1 >= 1)
        assert result.child_result is not None

    def test_chain_terminates_at_max_recursion_depth(self) -> None:
        # max_recursion_depth=2: chain is parent(0) → child(1) → grandchild(2) blocked
        # So chain length = 3 (parent + child + grandchild), grandchild has no child
        result, _, _ = _run_reinjection_cycle(max_recursion_depth=2)
        assert _chain_length(result) == 3
        # grandchild has no further child
        assert result.child_result.child_result.child_result is None  # type: ignore[union-attr]

    def test_child_session_stored_in_db(self) -> None:
        result, _, db_path = _run_reinjection_cycle(max_recursion_depth=1)
        child_result = result.child_result
        assert child_result is not None
        child_session = read_session(db_path, child_result.session_id)
        assert child_session is not None
        assert child_session.parent_session_id == result.session_id
        assert child_session.recursion_depth == 1

    def test_continuation_bundle_written_to_db(self) -> None:
        result, _, db_path = _run_reinjection_cycle(max_recursion_depth=1)
        child_result = result.child_result
        assert child_result is not None
        bundles = list_bundles_for_session(db_path, result.session_id)
        assert len(bundles) >= 1
        bundle = bundles[0]
        assert bundle.parent_session_id == result.session_id
        assert bundle.child_session_id == child_result.session_id

    def test_bundle_goal_preserved(self) -> None:
        result, _, db_path = _run_reinjection_cycle(max_recursion_depth=1)
        bundles = list_bundles_for_session(db_path, result.session_id)
        assert len(bundles) >= 1
        assert bundles[0].distilled_goal == "Build a feature."

    def test_child_cycle_also_hits_cap_reached(self) -> None:
        result, _, _ = _run_reinjection_cycle(max_recursion_depth=2)
        child = result.child_result
        assert child is not None
        # child also runs the same config → same stub → cap_reached
        assert child.outcome == "cap_reached"

    def test_no_reinjection_when_cycle_accepts(self) -> None:
        """A cycle that accepts should not spawn a child."""
        vault_path, db_path = _make_vault()
        from cerebra.cognition.cycle_config import _parse_config

        # Config with very low accept threshold (always accepts with score 0.55)
        data: dict[str, Any] = {
            "name": "test_always_accept",
            "version": 1,
            "description": "",
            "max_steps": 5,
            "max_recursion_depth": 3,
            "steps": [
                {
                    "name": "plan",
                    "description": "",
                    "prompt_template": {
                        "template": "{{ goal }}",
                        "expected_output_format": "free_form",
                    },
                }
            ],
            "stop_conditions": [{"name": "max", "type": "max_steps_reached", "parameters": {}}],
            "clutch_rules": [
                {
                    "name": "accept_low",
                    "description": "",
                    "predicate_name": "composite_above_threshold",
                    "action": "accept",
                    "parameters": {"threshold": 0.30},
                },
            ],
            "reinjection_triggers": [
                {"name": "t1", "predicate": "max_steps_without_acceptance", "parameters": {}}
            ],
        }
        config = _parse_config(data)
        store = FossicStore(vault_path)
        manager = SessionManager(db_path=db_path, store=store)
        session, opened_event_id = manager.open_session(
            vault_path=vault_path, goal="Test.", cycle_config=config.name
        )
        runtime = CycleRuntime(
            config, session, db_path, store, _StubLLM(score=0.55), opened_event_id
        )
        result = runtime.run()
        assert result.outcome == "accept"
        assert result.child_result is None

    def test_no_reinjection_when_triggers_empty(self) -> None:
        """Config with no reinjection_triggers → child_result is None even on cap_reached."""
        vault_path, db_path = _make_vault()
        data: dict[str, Any] = {
            "name": "test_no_triggers",
            "version": 1,
            "description": "",
            "max_steps": 2,
            "max_recursion_depth": 0,
            "steps": [
                {
                    "name": "plan",
                    "description": "",
                    "prompt_template": {
                        "template": "{{ goal }}",
                        "expected_output_format": "free_form",
                    },
                }
            ],
            "stop_conditions": [{"name": "max", "type": "max_steps_reached", "parameters": {}}],
            "clutch_rules": [
                {
                    "name": "accept_high",
                    "description": "",
                    "predicate_name": "composite_above_threshold",
                    "action": "accept",
                    "parameters": {"threshold": 0.99},
                },
                {
                    "name": "refine_always",
                    "description": "",
                    "predicate_name": "always",
                    "action": "refine",
                    "parameters": {},
                },
            ],
        }
        from cerebra.cognition.cycle_config import _parse_config

        config = _parse_config(data)
        store = FossicStore(vault_path)
        manager = SessionManager(db_path=db_path, store=store)
        session, opened_event_id = manager.open_session(
            vault_path=vault_path, goal="Test.", cycle_config=config.name
        )
        runtime = CycleRuntime(
            config, session, db_path, store, _StubLLM(score=0.55), opened_event_id
        )
        result = runtime.run()
        assert result.outcome == "cap_reached"
        assert result.child_result is None


class TestBanditArmStatsInheritance:

    def test_child_catalyst_engine_inherits_parent_arm_stats(self) -> None:
        """Child session CatalystEngine loads parent's arm_stats on first init."""
        from cerebra.cognition.catalyst import CatalystEngine
        from cerebra.cognition.cycle_config import CycleConfigLoader

        vault_path, db_path = _make_vault()
        store = FossicStore(vault_path)
        config = CycleConfigLoader().load("planning.adaptive.v0")
        manager = SessionManager(db_path=db_path, store=store)

        # Run parent cycle to accumulate arm_stats
        parent_session, parent_opened_event_id = manager.open_session(
            vault_path=vault_path, goal="Parent goal.", cycle_config=config.name
        )
        parent_runtime = CycleRuntime(
            config, parent_session, db_path, store, _StubLLM(score=0.55), parent_opened_event_id
        )
        parent_result = parent_runtime.run()

        # Verify parent has arm_stats
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT COUNT(*) FROM catalyst_arm_stats WHERE runtime_session_id = ?",
                (parent_session.session_id,),
            ).fetchone()
        finally:
            conn.close()
        parent_arm_count = rows[0] if rows else 0

        if parent_arm_count == 0:
            pytest.skip("Parent cycle did not invoke catalyst — cannot test inheritance")

        # Create child engine and verify it loads parent stats
        child_session, _ = manager.open_session(
            vault_path=vault_path,
            goal="Child goal.",
            cycle_config=config.name,
            parent_session_id=parent_session.session_id,
        )
        child_engine = CatalystEngine(
            session_id=child_session.session_id,
            db_path=db_path,
            arms=config.catalyst_arms,
            parent_session_id=parent_session.session_id,
        )
        # At least one arm should be loaded from parent (count > 0)
        has_inherited_stats = any(
            child_engine._bandit.get_stats(a.arm_id).count > 0 for a in config.catalyst_arms
        )
        assert has_inherited_stats, "Child CatalystEngine should inherit arm stats from parent"
