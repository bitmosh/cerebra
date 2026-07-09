# SPDX-License-Identifier: Apache-2.0
"""Phase 8 Step 3 unit tests — ContinuationBundle and BundleDistiller.

Run with: pytest tests/unit/test_continuation_bundle.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.cognition.continuation_bundle import (
    BundleDistiller,
    ContinuationBundle,
    _generate_bundle_id,
    _now_ms,
    link_child_session,
    list_bundles_for_session,
    read_bundle,
    write_bundle,
)
from cerebra.cognition.session import SessionManager
from cerebra.storage.fossic_store import FossicStore
from cerebra.storage.migrations import run_migrations

# ── ContinuationBundle dataclass ──────────────────────────────────────────────


class TestContinuationBundleDataclass:
    def _make_bundle(self, **overrides) -> ContinuationBundle:
        defaults = {
            "bundle_id": "bundle_abc123",
            "parent_session_id": "sess_parent001",
            "distilled_goal": "design a search feature",
            "summarized_prior_prompt": "Explored retrieval architecture.",
            "truth_tower_projection": {"t1": [], "t2": []},
            "cognitive_insights": ["Sparse beats dense for short queries"],
            "next_focus": "implement ranking layer",
            "open_questions": ["What latency budget?"],
            "constraints": ["No new deps without approval"],
            "recursion_depth": 0,
            "voice_mode": "default",
            "bundle_size_bytes": 512,
            "created_at": 1700000000000,
        }
        defaults.update(overrides)
        return ContinuationBundle(**defaults)

    def test_frozen(self) -> None:
        bundle = self._make_bundle()
        with pytest.raises((AttributeError, TypeError)):
            bundle.distilled_goal = "mutated"  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        bundle = self._make_bundle()
        assert bundle.bundle_id == "bundle_abc123"
        assert bundle.parent_session_id == "sess_parent001"
        assert bundle.distilled_goal == "design a search feature"
        assert bundle.recursion_depth == 0
        assert bundle.voice_mode == "default"

    def test_child_session_id_defaults_none(self) -> None:
        bundle = self._make_bundle()
        assert bundle.child_session_id is None

    def test_triggered_at_defaults_none(self) -> None:
        bundle = self._make_bundle()
        assert bundle.triggered_at is None

    def test_size_bytes_property(self) -> None:
        bundle = self._make_bundle(bundle_size_bytes=1024)
        assert bundle.size_bytes == 1024

    def test_to_prompt_prefix_contains_goal(self) -> None:
        bundle = self._make_bundle()
        prefix = bundle.to_prompt_prefix()
        assert "design a search feature" in prefix

    def test_to_prompt_prefix_contains_insights(self) -> None:
        bundle = self._make_bundle()
        prefix = bundle.to_prompt_prefix()
        assert "Sparse beats dense" in prefix

    def test_to_prompt_prefix_contains_open_questions(self) -> None:
        bundle = self._make_bundle()
        prefix = bundle.to_prompt_prefix()
        assert "What latency budget?" in prefix

    def test_to_prompt_prefix_contains_constraints(self) -> None:
        bundle = self._make_bundle()
        prefix = bundle.to_prompt_prefix()
        assert "No new deps" in prefix

    def test_to_prompt_prefix_no_empty_section_headers(self) -> None:
        bundle = self._make_bundle(
            cognitive_insights=[],
            open_questions=[],
            constraints=[],
        )
        prefix = bundle.to_prompt_prefix()
        # No section header should appear with nothing under it
        assert "Insights:" not in prefix
        assert "Open questions:" not in prefix
        assert "Constraints:" not in prefix

    def test_to_prompt_prefix_includes_recursion_depth(self) -> None:
        bundle = self._make_bundle(recursion_depth=2)
        prefix = bundle.to_prompt_prefix()
        assert "depth 2" in prefix


# ── BundleDistiller ───────────────────────────────────────────────────────────


class TestBundleDistiller:
    def test_returns_continuation_bundle(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p001", "build a feature", recursion_depth=0)
        assert isinstance(bundle, ContinuationBundle)

    def test_bundle_id_starts_with_bundle(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p001", "build a feature", recursion_depth=0)
        assert bundle.bundle_id.startswith("bundle_")

    def test_parent_session_id_preserved(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_myparent", "goal", recursion_depth=0)
        assert bundle.parent_session_id == "sess_myparent"

    def test_recursion_depth_preserved(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=3)
        assert bundle.recursion_depth == 3

    def test_voice_mode_preserved(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0, voice_mode="analytical")
        assert bundle.voice_mode == "analytical"

    def test_distilled_goal_is_goal(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "design caching layer", recursion_depth=0)
        assert bundle.distilled_goal == "design caching layer"

    def test_bundle_size_bytes_positive(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        assert bundle.bundle_size_bytes > 0

    def test_bundle_size_matches_json_content(self) -> None:
        import json

        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0, step_outputs=["step1 out"])
        raw = {
            "distilled_goal": bundle.distilled_goal,
            "summarized_prior_prompt": bundle.summarized_prior_prompt,
            "truth_tower_projection": bundle.truth_tower_projection,
            "cognitive_insights": bundle.cognitive_insights,
            "next_focus": bundle.next_focus,
            "open_questions": bundle.open_questions,
            "constraints": bundle.constraints,
        }
        expected = len(json.dumps(raw).encode())
        assert bundle.bundle_size_bytes == expected

    def test_summary_contains_goal(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "design a system", recursion_depth=0)
        assert "design a system" in bundle.summarized_prior_prompt

    def test_summary_capped_at_500_chars(self) -> None:
        d = BundleDistiller()
        long_output = "x" * 1000
        bundle = d.distill("sess_p", "goal", recursion_depth=0, step_outputs=[long_output])
        assert len(bundle.summarized_prior_prompt) <= 500

    def test_created_at_is_recent_ms(self) -> None:
        d = BundleDistiller()
        before = _now_ms()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        after = _now_ms()
        assert before <= bundle.created_at <= after

    def test_tower_data_passed_through(self) -> None:
        d = BundleDistiller()
        tower = {"t1": [{"id": "x"}], "t2": []}
        bundle = d.distill("sess_p", "goal", recursion_depth=0, tower_data=tower)
        assert bundle.truth_tower_projection == tower

    def test_no_tower_data_yields_empty_dict(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        assert bundle.truth_tower_projection == {}

    def test_v0_1_insights_empty(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0, step_outputs=["output"])
        assert bundle.cognitive_insights == []

    def test_v0_1_open_questions_empty(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        assert bundle.open_questions == []

    def test_v0_1_constraints_empty(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        assert bundle.constraints == []

    def test_child_session_id_is_none(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        assert bundle.child_session_id is None

    def test_triggered_at_is_none(self) -> None:
        d = BundleDistiller()
        bundle = d.distill("sess_p", "goal", recursion_depth=0)
        assert bundle.triggered_at is None


# ── Migration015 and persistence helpers ──────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "cerebra.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(path)
    return path


@pytest.fixture()
def store(tmp_path: Path) -> FossicStore:
    return FossicStore(tmp_path)


@pytest.fixture()
def session_id(db_path: Path, store: FossicStore, tmp_path: Path) -> str:
    mgr = SessionManager(db_path=db_path, store=store)
    session, _ = mgr.open_session(
        goal="test goal",
        cycle_config="test.v0",
        vault_path=tmp_path,
    )
    return session.session_id


def _make_bundle(parent_session_id: str, **overrides) -> ContinuationBundle:
    defaults = {
        "bundle_id": _generate_bundle_id(),
        "parent_session_id": parent_session_id,
        "distilled_goal": "goal",
        "summarized_prior_prompt": "summary",
        "truth_tower_projection": {},
        "cognitive_insights": [],
        "next_focus": "focus",
        "open_questions": [],
        "constraints": [],
        "recursion_depth": 0,
        "voice_mode": "default",
        "bundle_size_bytes": 100,
        "created_at": _now_ms(),
    }
    defaults.update(overrides)
    return ContinuationBundle(**defaults)


class TestMigration015:
    def test_table_exists_after_migration(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='continuation_bundles'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_indexes_created(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='continuation_bundles'"
            ).fetchall()
        }
        conn.close()
        assert "idx_bundles_parent" in indexes
        assert "idx_bundles_child" in indexes
        assert "idx_bundles_created" in indexes

    def test_migration_version_is_15(self) -> None:
        from cerebra.storage.migrations import Migration015_ContinuationBundles

        assert Migration015_ContinuationBundles.version == 15

    def test_migration_in_all_migrations(self) -> None:
        from cerebra.storage.migrations import ALL_MIGRATIONS, Migration015_ContinuationBundles

        types = [type(m) for m in ALL_MIGRATIONS]
        assert Migration015_ContinuationBundles in types

    def test_applied_migration_version_recorded(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT version FROM applied_migrations WHERE version = 15").fetchone()
        conn.close()
        assert row is not None


class TestBundlePersistence:
    def test_write_then_read_roundtrip(self, db_path: Path, session_id: str) -> None:
        bundle = _make_bundle(session_id, distilled_goal="roundtrip goal")
        write_bundle(db_path, bundle)
        loaded = read_bundle(db_path, bundle.bundle_id)
        assert loaded is not None
        assert loaded.distilled_goal == "roundtrip goal"
        assert loaded.bundle_id == bundle.bundle_id

    def test_read_nonexistent_returns_none(self, db_path: Path) -> None:
        assert read_bundle(db_path, "bundle_doesnotexist") is None

    def test_json_fields_roundtrip(self, db_path: Path, session_id: str) -> None:
        bundle = _make_bundle(
            session_id,
            truth_tower_projection={"t1": [{"id": "x"}]},
            cognitive_insights=["insight A"],
            open_questions=["Q1"],
            constraints=["C1"],
        )
        write_bundle(db_path, bundle)
        loaded = read_bundle(db_path, bundle.bundle_id)
        assert loaded is not None
        assert loaded.truth_tower_projection == {"t1": [{"id": "x"}]}
        assert loaded.cognitive_insights == ["insight A"]
        assert loaded.open_questions == ["Q1"]
        assert loaded.constraints == ["C1"]

    def test_list_bundles_for_session_empty(self, db_path: Path, session_id: str) -> None:
        assert list_bundles_for_session(db_path, session_id) == []

    def test_list_bundles_for_session_returns_all(self, db_path: Path, session_id: str) -> None:
        b1 = _make_bundle(session_id, created_at=1000000000001)
        b2 = _make_bundle(session_id, created_at=1000000000002)
        write_bundle(db_path, b1)
        write_bundle(db_path, b2)
        bundles = list_bundles_for_session(db_path, session_id)
        assert len(bundles) == 2

    def test_list_bundles_ordered_by_created_at(self, db_path: Path, session_id: str) -> None:
        b1 = _make_bundle(session_id, created_at=1000000000001)
        b2 = _make_bundle(session_id, created_at=1000000000003)
        b3 = _make_bundle(session_id, created_at=1000000000002)
        write_bundle(db_path, b1)
        write_bundle(db_path, b2)
        write_bundle(db_path, b3)
        bundles = list_bundles_for_session(db_path, session_id)
        assert [b.created_at for b in bundles] == [1000000000001, 1000000000002, 1000000000003]

    def test_link_child_session(
        self, db_path: Path, session_id: str, store: FossicStore, tmp_path: Path
    ) -> None:
        bundle = _make_bundle(session_id)
        write_bundle(db_path, bundle)

        # Create a second session to use as child
        mgr = SessionManager(db_path=db_path, store=store)
        child, _ = mgr.open_session(
            goal="child goal",
            cycle_config="test.v0",
            vault_path=tmp_path,
            parent_session_id=session_id,
        )

        link_child_session(db_path, bundle.bundle_id, child.session_id)
        loaded = read_bundle(db_path, bundle.bundle_id)
        assert loaded is not None
        assert loaded.child_session_id == child.session_id
        assert loaded.triggered_at is not None
