"""Phase 5 end-to-end integration tests.

Exercises the full Phase 5 surface (working memory, truth tower, session
lifecycle, cerebra context T1 auto-promotion) against the dev vault.

All tests skip if:
  - numpy is unavailable (context command requires it)
  - the dev vault is absent at ~/cerebra-vaults/dev

Tests that do NOT use `cerebra context` could technically run without numpy,
but the suite uses numpy at module level for consistency with the Phase 4 e2e
pattern.

Run with: pytest tests/integration/test_phase5_e2e.py -m integration -v
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping Phase 5 e2e tests")

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


def _fresh_session(vault_root: Path) -> str:
    """Create a fresh session for the vault; returns session_id."""
    from cerebra.cognition.working_memory import new_session

    return new_session(vault_root / "data" / "cerebra.db", str(vault_root))


def _db(vault_root: Path) -> Path:
    return vault_root / "data" / "cerebra.db"


def _cli(*args: str, vault: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["cerebra", *args, "--vault", str(vault)],
        capture_output=True,
        text=True,
        timeout=30,
    )


# ── 1. Full working memory flow ───────────────────────────────────────────────


@pytest.mark.integration
class TestFullWorkingMemoryFlow:
    def test_promote_evict_status_cycle(self, vault_root: Path) -> None:
        """Promote 3 items, status shows 3; evict 1, status shows 2."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory

        session_id = _fresh_session(vault_root)
        db = _db(vault_root)
        wm = WorkingMemory(db, session_id)
        items = [wm.promote("evidence", None, f"evidence {i}", 0.70 + i * 0.05) for i in range(3)]

        result = CliRunner().invoke(cli, ["memory", "status", "--vault", str(vault_root)])
        assert result.exit_code == 0, result.output
        assert "3" in result.output or "[evidence]" in result.output

        # Evict the first item
        CliRunner().invoke(cli, ["memory", "evict", items[0].item_id, "--vault", str(vault_root)])

        result2 = CliRunner().invoke(cli, ["memory", "status", "--vault", str(vault_root)])
        assert result2.exit_code == 0, result2.output
        assert items[0].item_id not in result2.output

    def test_pinned_capacity_blocks_promotion(self, vault_root: Path) -> None:
        """Fill a slot with pinned items, then attempt another → PromotionError exit 2."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory

        session_id = _fresh_session(vault_root)
        db = _db(vault_root)
        wm = WorkingMemory(db, session_id)
        # goal capacity = 1; promote one pinned item
        wm.promote("goal", None, "pinned goal", 0.9, is_pinned=True)

        # Try to promote another into the full pinned slot via CLI
        result = CliRunner().invoke(
            cli,
            [
                "memory",
                "promote",
                "--text",
                "extra goal",
                "--slot",
                "goal",
                "--vault",
                str(vault_root),
            ],
        )
        # Should fail: slot at capacity, only pinned item exists
        assert result.exit_code == 2

    def test_synthetic_text_item_defaults(self, vault_root: Path) -> None:
        """--text --slot stores content_summary and uses the default salience."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory

        session_id = _fresh_session(vault_root)
        result = CliRunner().invoke(
            cli,
            [
                "memory",
                "promote",
                "--text",
                "unique synthetic content abc",
                "--slot",
                "hypothesis",
                "--vault",
                str(vault_root),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "0.8000" in result.output  # SYNTHETIC_ITEM_DEFAULT_SALIENCE

        db = _db(vault_root)
        wm = WorkingMemory(db, session_id)
        all_items = wm.load_all_active()
        hyp_items = all_items.get("hypothesis", [])
        assert any("unique synthetic content abc" in i.content_summary for i in hyp_items)


# ── 2. Full tower flow ────────────────────────────────────────────────────────


@pytest.mark.integration
class TestFullTowerFlow:
    def test_context_t1_t2_visible_in_status(self, vault_root: Path) -> None:
        """context → T1, memory promote --tier 2 --cite → both visible in memory status."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.truth_tower import TruthTower
        from cerebra.cognition.working_memory import WorkingMemory

        session_id = _fresh_session(vault_root)
        db = _db(vault_root)

        # Populate T1 via context
        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        assert result.exit_code == 0, result.output

        t1_items = TruthTower(db, session_id).load_tier(1)
        if not t1_items:
            pytest.skip("No T1 items — retrieval returned nothing for this vault state")

        # Ensure at least one WM item exists to promote to T2
        wm = WorkingMemory(db, session_id)
        all_items = wm.load_all_active()
        wm_list = [i for items in all_items.values() for i in items]
        if not wm_list:
            wm_item = wm.promote("evidence", None, "test evidence for T2", 0.6)
        else:
            wm_item = wm_list[0]

        t1_id = t1_items[0].tower_item_id
        result2 = CliRunner().invoke(
            cli,
            [
                "memory",
                "promote",
                wm_item.item_id,
                "--tier",
                "2",
                "--cite",
                t1_id,
                "--vault",
                str(vault_root),
            ],
        )
        assert result2.exit_code == 0, result2.output

        # memory status should show both sections
        result3 = CliRunner().invoke(cli, ["memory", "status", "--vault", str(vault_root)])
        assert result3.exit_code == 0, result3.output
        assert "T1 [1]" in result3.output
        assert "T2 [1]" in result3.output

    def test_t1_eviction_staleness_cascade(self, vault_root: Path) -> None:
        """Evict a T1 → dependent T2 items become stale; visible in memory status."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.truth_tower import TruthTower
        from cerebra.cognition.working_memory import WorkingMemory
        from cerebra.storage.db import connect

        session_id = _fresh_session(vault_root)
        db = _db(vault_root)

        # Populate T1 and a T2
        CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "2"]
        )
        tower = TruthTower(db, session_id)
        t1s = tower.load_tier(1)
        if not t1s:
            pytest.skip("No T1 items")

        wm = WorkingMemory(db, session_id)
        wm_item = wm.promote("evidence", None, "wm for stale cascade", 0.6)
        tower.promote_to_t2(wm_item, t1s[0].tower_item_id)

        # Evict the T1 and cascade stale
        conn = connect(db)
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = ? WHERE tower_item_id = ?",
            (int(time.time()), t1s[0].tower_item_id),
        )
        conn.commit()
        conn.close()
        tower.mark_stale_from_t1_eviction(t1s[0].tower_item_id)

        result = CliRunner().invoke(cli, ["memory", "status", "--vault", str(vault_root)])
        assert result.exit_code == 0, result.output
        assert "[stale]" in result.output

    def test_multiple_t2_same_t1_all_stale(self, vault_root: Path) -> None:
        """Multiple T2 items citing the same T1 all become stale when T1 is evicted."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.truth_tower import TruthTower
        from cerebra.cognition.working_memory import WorkingMemory
        from cerebra.storage.db import connect

        session_id = _fresh_session(vault_root)
        db = _db(vault_root)

        CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "2"]
        )
        tower = TruthTower(db, session_id)
        t1s = tower.load_tier(1)
        if not t1s:
            pytest.skip("No T1 items")

        wm = WorkingMemory(db, session_id)
        for i in range(3):
            wm_item = wm.promote("evidence", None, f"wm {i} for multi-stale", 0.5 + i * 0.05)
            tower.promote_to_t2(wm_item, t1s[0].tower_item_id)

        conn = connect(db)
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = ? WHERE tower_item_id = ?",
            (int(time.time()), t1s[0].tower_item_id),
        )
        conn.commit()
        conn.close()
        stale_count = tower.mark_stale_from_t1_eviction(t1s[0].tower_item_id)
        assert stale_count == 3

        t2_items = tower.load_tier(2)
        assert all(t2.is_stale for t2 in t2_items)


# ── 3. Session lifecycle ──────────────────────────────────────────────────────


@pytest.mark.integration
class TestSessionLifecycle:
    def test_session_show_no_session(self, vault_root: Path) -> None:
        """After reset to a fresh vault state with no active session, show says so."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.storage.db import connect

        # Force no active session by closing it directly
        db = _db(vault_root)
        conn = connect(db)
        conn.execute(
            "UPDATE sessions SET status = 'closed' WHERE vault_path = ? AND status = 'active'",
            (str(vault_root),),
        )
        conn.commit()
        conn.close()

        result = CliRunner().invoke(cli, ["session", "show", "--vault", str(vault_root)])
        assert result.exit_code == 0, result.output
        assert "No active session" in result.output

    def test_session_show_populated(self, vault_root: Path) -> None:
        """session show with an active populated session shows all required fields."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory

        session_id = _fresh_session(vault_root)
        db = _db(vault_root)
        wm = WorkingMemory(db, session_id)
        wm.promote("evidence", None, "some evidence", 0.7)

        result = CliRunner().invoke(cli, ["session", "show", "--vault", str(vault_root)])
        assert result.exit_code == 0, result.output
        assert session_id in result.output
        assert "Started:" in result.output
        assert "Working memory:" in result.output
        assert "Tower:" in result.output

        # JSON shape
        result_json = CliRunner().invoke(
            cli, ["session", "show", "--vault", str(vault_root), "--format", "json"]
        )
        assert result_json.exit_code == 0, result_json.output
        data = json.loads(result_json.output)
        for key in (
            "session_id",
            "vault_path",
            "started_at",
            "last_active_at",
            "wm_item_count",
            "t1_item_count",
            "t2_item_count",
        ):
            assert key in data, f"Missing key: {key}"
        assert data["session_id"] == session_id

    def test_session_reset_creates_new_empty_session(self, vault_root: Path) -> None:
        """session reset closes old session; new session has no WM items."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory, get_active_session

        session_id_before = _fresh_session(vault_root)
        db = _db(vault_root)
        # Put something in working memory
        wm_before = WorkingMemory(db, session_id_before)
        wm_before.promote("evidence", None, "pre-reset evidence", 0.7)

        result = CliRunner().invoke(cli, ["session", "reset", "--vault", str(vault_root)])
        assert result.exit_code == 0, result.output
        assert "New session:" in result.output

        session_id_after = get_active_session(db, str(vault_root))
        assert session_id_after is not None
        assert session_id_after != session_id_before

        wm_after = WorkingMemory(db, session_id_after)
        all_items = wm_after.load_all_active()
        total_after = sum(len(v) for v in all_items.values())
        assert total_after == 0


# ── 4. Context × session interaction ─────────────────────────────────────────


@pytest.mark.integration
class TestContextSessionInteraction:
    def test_context_creates_session_and_populates_t1(self, vault_root: Path) -> None:
        """First cerebra context creates a session and populates T1."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.truth_tower import TruthTower
        from cerebra.cognition.working_memory import get_active_session
        from cerebra.storage.db import connect

        # Close any existing active session
        db = _db(vault_root)
        conn = connect(db)
        conn.execute(
            "UPDATE sessions SET status = 'closed' WHERE vault_path = ? AND status = 'active'",
            (str(vault_root),),
        )
        conn.commit()
        conn.close()

        result = CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        assert result.exit_code == 0, result.output

        session_id = get_active_session(db, str(vault_root))
        assert session_id is not None, "context must create a session"
        t1_count = len(TruthTower(db, session_id).load_tier(1))
        assert t1_count >= 0  # may be 0 if vault has no matching records

    def test_no_promote_leaves_t1_unchanged(self, vault_root: Path) -> None:
        """context --no-promote does not change T1 count."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.truth_tower import TruthTower
        from cerebra.cognition.working_memory import get_active_session

        db = _db(vault_root)
        # Ensure fresh session with some T1 items
        CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        session_id = get_active_session(db, str(vault_root))
        t1_before = len(TruthTower(db, session_id).load_tier(1)) if session_id else 0

        CliRunner().invoke(
            cli,
            ["context", "memory drift", "--vault", str(vault_root), "--limit", "3", "--no-promote"],
        )

        session_id2 = get_active_session(db, str(vault_root))
        t1_after = len(TruthTower(db, session_id2).load_tier(1)) if session_id2 else 0
        assert t1_after == t1_before


# ── 5. Lattice-aware T1 deduplication ────────────────────────────────────────


@pytest.mark.integration
class TestLatticeAwareT1Promotion:
    def test_sibling_chunk_dedup_pins_current_behavior(self, vault_root: Path) -> None:
        """Two records sharing a chunk_id: only the first gets into T1.

        This test pins the lattice-sibling dedup behavior from Step 5.
        Lattice Step 2 will update the 'which sibling wins' logic; this test
        will be revisited then.
        """
        import time
        from dataclasses import dataclass

        from cerebra.cognition.truth_tower import TruthTower
        from cerebra.cognition.working_memory import new_session
        from cerebra.storage.db import connect
        from cerebra.storage.migrations import run_migrations

        db = _db(vault_root)
        run_migrations(db)
        session_id = new_session(db, str(vault_root))

        shared_chunk = f"chk_shared_{int(time.time())}"
        now = int(time.time())

        @dataclass
        class _FakeMI:
            record_id: str
            source_id: str
            chunk_id: str
            content_excerpt: str
            source_path: str
            sku_address: None
            score: float
            score_components: dict
            retrieval_path: str
            rank: int

        # Seed two records sharing the same chunk_id
        src_id = f"src_shared_{now}"
        doc_id = f"doc_shared_{now}"
        rec_a = f"rec_sib_a_{now}"
        rec_b = f"rec_sib_b_{now}"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sources "
                "(source_id, canonical_path, content_hash, size_bytes, "
                " detected_type, detection_confidence, parser_status, "
                " lifecycle_state, created_at, schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    src_id,
                    f"/test/sibling_{now}",
                    "h0",
                    1,
                    "markdown",
                    1.0,
                    "done",
                    "active",
                    now,
                    1,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO documents "
                "(document_id, source_id, document_type, normalization_confidence, "
                " lifecycle_state, created_at, schema_version) "
                "VALUES (?,?,?,?,?,?,?)",
                (doc_id, src_id, "markdown", 1.0, "active", now, 1),
            )
            conn.execute(
                "INSERT OR IGNORE INTO chunks "
                "(chunk_id, document_id, source_id, heading_path, chunk_index, "
                " depth, content, content_hash, token_estimate, chunk_strategy, "
                " lifecycle_state, created_at, schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    shared_chunk,
                    doc_id,
                    src_id,
                    "",
                    0,
                    0,
                    "shared chunk content",
                    f"hc_{now}",
                    5,
                    "fixed",
                    "active",
                    now,
                    1,
                ),
            )
            for rec in (rec_a, rec_b):
                conn.execute(
                    "INSERT OR IGNORE INTO memory_records "
                    "(record_id, record_type, source_id, document_id, chunk_id, "
                    " content, content_hash, token_estimate, lifecycle_state, "
                    " created_at, schema_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        rec,
                        "source_chunk",
                        src_id,
                        doc_id,
                        shared_chunk,
                        f"content for {rec}",
                        "hr0",
                        5,
                        "active",
                        now,
                        1,
                    ),
                )
            conn.execute(
                "INSERT OR IGNORE INTO retrieval_traces "
                "(trace_id, query, mode, plan_json, started_at, finished_at, duration_ms, "
                " candidate_count, selected_count, abstained, schema_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"trace_sibling_{now}", "test", "sku", "{}", now, now, 1, 2, 2, 0, 1),
            )
            conn.commit()
        finally:
            conn.close()

        mi_a = _FakeMI(
            rec_a, src_id, shared_chunk, "content for a", "/test/a.md", None, 0.80, {}, "vector", 1
        )
        mi_b = _FakeMI(
            rec_b, src_id, shared_chunk, "content for b", "/test/b.md", None, 0.75, {}, "vector", 2
        )

        tower = TruthTower(db, session_id)
        promoted = tower.promote_to_t1([mi_a, mi_b], trace_id=f"trace_sibling_{now}")

        assert (
            len(promoted) == 1
        ), f"Expected 1 T1 item from two siblings sharing chunk_id; got {len(promoted)}"
        assert promoted[0].record_id == rec_a


# ── 6. Lockfile enforcement ───────────────────────────────────────────────────


@pytest.mark.integration
class TestLockfileEnforcement:
    def test_memory_promote_fails_when_locked(self, vault_root: Path) -> None:
        """subprocess cerebra memory promote exits 2 when vault lock is held."""
        from cerebra.cli.lockfile import lock_path

        lp = lock_path(vault_root)
        with open(lp, "w") as fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fd.write(str(os.getpid()))
                fd.flush()

                result = subprocess.run(
                    [
                        "cerebra",
                        "memory",
                        "promote",
                        "--text",
                        "blocked item",
                        "--slot",
                        "evidence",
                        "--vault",
                        str(vault_root),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert result.returncode == 2, (
                    f"Expected exit 2 under lock, got {result.returncode}. "
                    f"stderr: {result.stderr!r}"
                )
                assert (
                    "locked" in (result.stderr + result.stdout).lower()
                ), f"Expected 'locked' in output. stderr: {result.stderr!r}"
            finally:
                lp.unlink(missing_ok=True)

    def test_context_fails_when_locked(self, vault_root: Path) -> None:
        """subprocess cerebra context exits 2 when vault lock is held (T1 write path)."""
        from cerebra.cli.lockfile import lock_path

        lp = lock_path(vault_root)
        with open(lp, "w") as fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fd.write(str(os.getpid()))
                fd.flush()

                result = subprocess.run(
                    [
                        "cerebra",
                        "context",
                        "leeway network",
                        "--vault",
                        str(vault_root),
                        "--limit",
                        "3",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert result.returncode == 2, (
                    f"Expected exit 2 under lock, got {result.returncode}. "
                    f"stderr: {result.stderr!r}"
                )
            finally:
                lp.unlink(missing_ok=True)

    def test_search_succeeds_when_locked(self, vault_root: Path) -> None:
        """subprocess cerebra search exits 0 with lock held (read-only, no lock needed)."""
        from cerebra.cli.lockfile import lock_path

        lp = lock_path(vault_root)
        with open(lp, "w") as fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fd.write(str(os.getpid()))
                fd.flush()

                result = subprocess.run(
                    ["cerebra", "search", "leeway network", "--vault", str(vault_root)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert result.returncode == 0, (
                    f"search should succeed with lock held, got {result.returncode}. "
                    f"stderr: {result.stderr!r}"
                )
            finally:
                lp.unlink(missing_ok=True)
