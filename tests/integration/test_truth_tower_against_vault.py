"""
Integration tests for TruthTower against a real (migrated) dev vault DB.

These tests confirm:
  1. Migration009 truth_tower_items table is present in the vault DB.
  2. T1 can be promoted against real memory_records (FK chain intact).
  3. T2 can be promoted citing a real T1 row.
  4. Stale cascade reaches real T2 rows after T1 eviction.
  5. render_chronological produces non-empty output for a populated tower.

The vault path is read from CEREBRA_TEST_VAULT env var if set, else falls back
to ~/cerebra-vaults/dev/.  All tests are skipped (not failed) when the vault DB
is absent so CI (which has no vaults) stays green.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from cerebra.cognition.truth_tower import TruthTower
from cerebra.cognition.working_memory import WorkingMemory, new_session
from cerebra.storage.db import connect

# ── vault fixture ─────────────────────────────────────────────────────────────


def _vault_db() -> Path | None:
    env_vault = os.environ.get("CEREBRA_TEST_VAULT")
    if env_vault:
        candidate = Path(env_vault) / "data" / "cerebra.db"
    else:
        candidate = Path.home() / "cerebra-vaults" / "dev" / "data" / "cerebra.db"
    return candidate if candidate.exists() else None


@pytest.fixture(scope="module")
def vault_db() -> Path:
    db = _vault_db()
    if db is None:
        pytest.skip("No vault DB found; set CEREBRA_TEST_VAULT or populate ~/cerebra-vaults/dev/")
    return db


@pytest.fixture
def session_id(vault_db: Path) -> str:
    vault_path = str(vault_db.parent.parent)
    return new_session(vault_db, vault_path=vault_path)


@pytest.fixture
def tower(vault_db: Path, session_id: str) -> TruthTower:
    return TruthTower(vault_db, session_id)


def _seed_trace(db: Path, trace_id: str = "trace_integ") -> str:
    """Insert a minimal retrieval_trace row (idempotent via OR IGNORE)."""
    now = int(time.time())
    conn = connect(db)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO retrieval_traces "
            "(trace_id, query, mode, plan_json, started_at, finished_at, "
            " duration_ms, candidate_count, selected_count, abstained, schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (trace_id, "integration test", "sku", "{}", now, now, 1, 3, 2, 0, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return trace_id


def _first_real_records(db: Path, n: int = 3) -> list[dict]:
    """Return up to n real memory_records from the vault DB."""
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT record_id, chunk_id, sku_address "
            "FROM memory_records "
            "WHERE lifecycle_state = 'active' "
            "ORDER BY created_at DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


class _FakeMemoryItem:
    """Minimal MemoryItem stand-in built from a real DB record."""

    def __init__(self, row: dict) -> None:
        self.record_id = row["record_id"]
        self.source_id = "src_fake"
        self.chunk_id = row["chunk_id"] or f"chk_{row['record_id']}"
        self.content_excerpt = "Integration test content excerpt"
        self.source_path = "/integration/test.md"
        self.sku_address = row.get("sku_address")
        self.score = 0.75
        self.score_components: dict = {}
        self.retrieval_path = "sku"
        self.rank = 0


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestTruthTowerAgainstVault:
    def test_truth_tower_items_table_exists(self, vault_db: Path) -> None:
        """Migration009 must have created the truth_tower_items table."""
        conn = connect(vault_db)
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert "truth_tower_items" in tables

    def test_promote_real_records_to_t1(
        self, vault_db: Path, tower: TruthTower
    ) -> None:
        """Promote real vault records into T1 — FK constraints must pass."""
        rows = _first_real_records(vault_db, n=2)
        if not rows:
            pytest.skip("No active memory_records in vault")

        trace_id = _seed_trace(vault_db, "trace_integ_t1")
        fake_items = [_FakeMemoryItem(r) for r in rows]

        result = tower.promote_to_t1(fake_items, trace_id)
        assert len(result) >= 1
        for item in result:
            assert item.tier == 1
            assert item.session_id == tower.session_id

    def test_promote_t2_citing_real_t1(
        self, vault_db: Path, tower: TruthTower, session_id: str
    ) -> None:
        """Promote one T2 citing a T1 created from real vault data."""
        rows = _first_real_records(vault_db, n=1)
        if not rows:
            pytest.skip("No active memory_records in vault")

        trace_id = _seed_trace(vault_db, "trace_integ_t2")
        t1_items = tower.promote_to_t1([_FakeMemoryItem(rows[0])], trace_id)
        if not t1_items:
            pytest.skip("Could not promote any T1 (possibly idempotent from prior run)")

        t1 = t1_items[0]
        wm = WorkingMemory(vault_db, session_id)
        wm_item = wm.promote("evidence", rows[0]["record_id"], "Integration T2 evidence", salience_score=0.65)

        t2 = tower.promote_to_t2(wm_item, t1.tower_item_id)
        assert t2.tier == 2
        assert t2.t1_citation_id == t1.tower_item_id
        assert not t2.is_stale

    def test_stale_cascade_on_real_data(
        self, vault_db: Path, tower: TruthTower, session_id: str
    ) -> None:
        """Evicting a T1 must mark all its T2 children is_stale=1 in vault DB."""
        rows = _first_real_records(vault_db, n=1)
        if not rows:
            pytest.skip("No active memory_records in vault")

        trace_id = _seed_trace(vault_db, "trace_integ_stale")
        t1_items = tower.promote_to_t1([_FakeMemoryItem(rows[0])], trace_id)
        if not t1_items:
            pytest.skip("Could not promote T1 — possibly idempotent from prior run")

        t1 = t1_items[0]
        wm = WorkingMemory(vault_db, session_id)
        wm_item = wm.promote("hypothesis", None, "T2 hypothesis citing real T1", salience_score=0.55)
        tower.promote_to_t2(wm_item, t1.tower_item_id)

        stale_count = tower.mark_stale_from_t1_eviction(t1.tower_item_id)
        assert stale_count >= 1

        t2_active = tower.load_tier(2)
        citing = [i for i in t2_active if i.t1_citation_id == t1.tower_item_id]
        assert all(c.is_stale for c in citing)

    def test_render_chronological_nonempty(
        self, vault_db: Path, tower: TruthTower
    ) -> None:
        """render_chronological must return a non-empty string after a T1 promotion."""
        rows = _first_real_records(vault_db, n=2)
        if not rows:
            pytest.skip("No active memory_records in vault")

        trace_id = _seed_trace(vault_db, "trace_integ_render")
        tower.promote_to_t1([_FakeMemoryItem(r) for r in rows], trace_id)

        rendered = tower.render_chronological()
        assert rendered, "render_chronological returned empty string"
        assert "T1 [1]" in rendered
        assert "score:" in rendered
