"""
Integration smoke test: interpretive lattice against the dev vault.

Uses ~/cerebra-vaults/dev. Skips if absent.
Only verifies the Migration010 columns exist; does not run a real LLM call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_VAULT_DB = Path.home() / "cerebra-vaults" / "dev" / "data" / "cerebra.db"


@pytest.fixture(scope="module")
def vault_db() -> Path:
    if not _VAULT_DB.exists():
        pytest.skip(f"Dev vault not found at {_VAULT_DB}")
    return _VAULT_DB


@pytest.mark.integration
class TestLatticeColumnsOnVault:
    def test_migration010_columns_exist(self, vault_db: Path) -> None:
        """After run_migrations, memory_records has the three lattice columns."""
        from cerebra.storage.db import connect
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        conn = connect(vault_db)
        try:
            row = conn.execute("PRAGMA table_info(memory_records)").fetchall()
        finally:
            conn.close()

        col_names = {r[1] for r in row}
        assert "lattice_lineage_id" in col_names
        assert "is_lattice_member" in col_names
        assert "lattice_confidence" in col_names

    def test_existing_records_have_default_lattice_state(self, vault_db: Path) -> None:
        """All pre-existing records default to is_lattice_member=0, lineage_id=NULL."""
        from cerebra.storage.db import connect
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        conn = connect(vault_db)
        try:
            non_lattice = conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE is_lattice_member != 0"
            ).fetchone()[0]
            non_null_lineage = conn.execute(
                "SELECT COUNT(*) FROM memory_records "
                "WHERE lattice_lineage_id IS NOT NULL AND is_lattice_member = 0"
            ).fetchone()[0]
        finally:
            conn.close()

        assert non_lattice == 0, f"{non_lattice} pre-existing records have is_lattice_member != 0"
        assert non_null_lineage == 0
