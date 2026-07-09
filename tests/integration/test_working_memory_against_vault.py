# SPDX-License-Identifier: Apache-2.0
"""Integration tests: WorkingMemory against the dev vault.

Uses the real SQLite database at ~/cerebra-vaults/dev/data/cerebra.db.
Skips automatically if the vault is absent.

Run with: pytest tests/integration/test_working_memory_against_vault.py -m integration -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cerebra.cognition._constants import SLOT_CAPACITIES
from cerebra.cognition.working_memory import (
    PromotionError,
    WorkingMemory,
    new_session,
)

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"
_VAULT_PATH = str(_VAULT_ROOT)


@pytest.fixture(scope="module")
def vault_db() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_DB


@pytest.fixture()
def wm(vault_db: Path) -> WorkingMemory:
    """Fresh session for each test; returns a WorkingMemory bound to it."""
    session_id = new_session(vault_db, vault_path=_VAULT_PATH)
    return WorkingMemory(vault_db, session_id)


@pytest.mark.integration
class TestWorkingMemoryVaultIntegration:
    def test_promote_persists_across_instances(self, vault_db: Path, wm: WorkingMemory) -> None:
        """Item written via one WorkingMemory instance is visible from another."""
        item = wm.promote("goal", None, "integration goal", salience_score=0.7)
        wm2 = WorkingMemory(vault_db, wm.session_id)
        loaded = wm2.load_slot("goal")
        assert any(i.item_id == item.item_id for i in loaded)

    def test_load_all_active_vault_round_trip(self, vault_db: Path, wm: WorkingMemory) -> None:
        """Items placed in multiple slots survive a full round-trip via load_all_active."""
        wm.promote("goal", None, "vault goal", salience_score=0.5)
        wm.promote("context", None, "vault ctx", salience_score=0.4)
        wm.promote("evidence", None, "vault ev", salience_score=0.6)
        result = wm.load_all_active()
        assert len(result["goal"]) >= 1
        assert len(result["context"]) >= 1
        assert len(result["evidence"]) >= 1

    def test_eviction_respects_capacity_against_vault(self, wm: WorkingMemory) -> None:
        """Slot never exceeds its declared capacity on the vault DB."""
        cap = SLOT_CAPACITIES["contradiction"]  # 2
        for i in range(cap + 2):
            wm.promote("contradiction", None, f"item {i}", salience_score=float(i) / 10)
        active = wm.load_slot("contradiction")
        assert len(active) <= cap, f"Slot exceeded capacity: {len(active)} > {cap}"

    def test_explicit_evict_vault(self, wm: WorkingMemory) -> None:
        """Explicit evict removes item from vault DB."""
        item = wm.promote("hypothesis", None, "temp hypothesis", salience_score=0.5)
        wm.evict(item.item_id, reason="integration_test")
        active = wm.load_slot("hypothesis")
        assert all(i.item_id != item.item_id for i in active)

    def test_session_isolation_vault(self, vault_db: Path, wm: WorkingMemory) -> None:
        """Items from one session do not appear in a different session's load_all_active."""
        wm.promote("goal", None, "session A item", salience_score=0.8)
        sid_b = new_session(vault_db, vault_path=_VAULT_PATH)
        wm_b = WorkingMemory(vault_db, sid_b)
        result_b = wm_b.load_all_active()
        all_items_b = [i for items in result_b.values() for i in items]
        assert all(i.session_id == sid_b for i in all_items_b)

    def test_render_text_vault(self, wm: WorkingMemory) -> None:
        """render_text returns non-empty string containing slot names."""
        wm.promote("procedure", None, "do the thing", salience_score=0.6)
        text = wm.render_text()
        assert isinstance(text, str) and len(text) > 0
        assert "procedure" in text

    def test_to_dict_vault(self, wm: WorkingMemory) -> None:
        """to_dict returns JSON-serialisable dict with all 10 slot keys."""
        import json

        wm.promote("question", None, "what?", salience_score=0.4)
        d = wm.to_dict()
        serialised = json.dumps(d)
        assert len(serialised) > 0
        assert set(d["slots"].keys()) == set(SLOT_CAPACITIES.keys())

    def test_pinned_item_survives_eviction_vault(self, wm: WorkingMemory) -> None:
        """Pinned items must never be evicted even after many promotions."""
        pinned = wm.promote(
            "contradiction", None, "pinned item", salience_score=0.1, is_pinned=True
        )
        cap = SLOT_CAPACITIES["contradiction"]
        for i in range(cap + 3):
            try:
                wm.promote(
                    "contradiction",
                    None,
                    f"filler {i}",
                    salience_score=0.9 - float(i) * 0.05,
                )
            except PromotionError:
                break
        active = wm.load_slot("contradiction")
        ids = {i.item_id for i in active}
        assert pinned.item_id in ids, "Pinned item must survive repeated eviction pressure"

    def test_to_dict_item_count_matches_load_all(self, wm: WorkingMemory) -> None:
        """to_dict total_item_count matches the sum of load_all_active lengths."""
        wm.promote("goal", None, "g", salience_score=0.5)
        wm.promote("context", None, "c", salience_score=0.4)
        d = wm.to_dict()
        result = wm.load_all_active()
        expected_count = sum(len(items) for items in result.values())
        assert d["total_item_count"] == expected_count
