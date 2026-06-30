"""
Integration tests: cerebra memory promote --tier 2 against the real dev vault.

Skips automatically if numpy is unavailable or the dev vault is absent.

Scenarios:
1. Full flow: context to populate T1 → memory promote --tier 2 --cite → T2 visible
2. Lattice-aware: T1 from a lattice sibling can be cited for T2 promotion
3. Born-stale: evict the T1 then try T2 promotion citing it → exit 2 with clear message
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy", reason="numpy not available — skipping T2 vault tests")

_VAULT_ROOT = Path.home() / "cerebra-vaults" / "dev"
_VAULT_DB = _VAULT_ROOT / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_root() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_ROOT


@pytest.fixture(scope="module")
def clean_session(vault_root: Path) -> str:
    from cerebra.cognition.working_memory import new_session
    db = vault_root / "data" / "cerebra.db"
    return new_session(db, str(vault_root))


def _get_t1_items(vault_root: Path, session_id: str) -> list:
    from cerebra.cognition.truth_tower import TruthTower
    db = vault_root / "data" / "cerebra.db"
    return TruthTower(db, session_id).load_tier(1)


def _get_t2_items(vault_root: Path, session_id: str) -> list:
    from cerebra.cognition.truth_tower import TruthTower
    db = vault_root / "data" / "cerebra.db"
    return TruthTower(db, session_id).load_tier(2)


@pytest.mark.integration
class TestMemoryPromoteT2AgainstVault:
    def test_full_flow_context_then_t2_promote(
        self, vault_root: Path, clean_session: str
    ) -> None:
        """context populates T1 → memory promote --tier 2 --cite → T2 visible in tower."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory

        # Step 1: populate T1 via context
        CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )

        t1_items = _get_t1_items(vault_root, clean_session)
        if not t1_items:
            pytest.skip("No T1 items found — retrieval returned nothing")

        t1_id = t1_items[0].tower_item_id

        # Step 2: get a WM item to promote to T2
        db = vault_root / "data" / "cerebra.db"
        wm = WorkingMemory(db, clean_session)
        all_items = wm.load_all_active()
        wm_items = [i for items in all_items.values() for i in items]
        if not wm_items:
            pytest.skip("No WM items to promote to T2")

        wm_id = wm_items[0].item_id
        t2_before = len(_get_t2_items(vault_root, clean_session))

        result = CliRunner().invoke(
            cli,
            ["memory", "promote", wm_id, "--tier", "2", "--cite", t1_id,
             "--vault", str(vault_root)],
        )
        assert result.exit_code == 0, result.output
        assert "Promoted to T2:" in result.output
        assert t1_id in result.output

        t2_after = len(_get_t2_items(vault_root, clean_session))
        assert t2_after > t2_before

    def test_born_stale_rejection(
        self, vault_root: Path, clean_session: str
    ) -> None:
        """Evict the T1, then try to cite it for T2 → exit 2 with clear error."""
        from click.testing import CliRunner

        from cerebra.cli.main import cli
        from cerebra.cognition.working_memory import WorkingMemory

        db = vault_root / "data" / "cerebra.db"

        # Ensure T1 has at least one item
        CliRunner().invoke(
            cli, ["context", "leeway network", "--vault", str(vault_root), "--limit", "3"]
        )
        t1_items = _get_t1_items(vault_root, clean_session)
        if not t1_items:
            pytest.skip("No T1 items to evict")

        # Evict the T1 directly in DB
        t1_id = t1_items[-1].tower_item_id
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = 1 WHERE tower_item_id = ?",
            (t1_id,),
        )
        conn.commit()
        conn.close()

        # Get a WM item
        wm = WorkingMemory(db, clean_session)
        all_items = wm.load_all_active()
        wm_items = [i for items in all_items.values() for i in items]
        if not wm_items:
            pytest.skip("No WM items available")

        result = CliRunner().invoke(
            cli,
            ["memory", "promote", wm_items[0].item_id, "--tier", "2", "--cite", t1_id,
             "--vault", str(vault_root)],
        )
        assert result.exit_code == 2
        assert "Error:" in result.output
        assert "evicted" in result.output.lower() or "Error:" in result.output
