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

    def test_lattice_column_schema(self, vault_db: Path) -> None:
        """Migration010 wires up the lattice columns with the correct schema.

        Checks PRAGMA table_info rather than vault data — the vault accumulates
        real lattice members over time as classify runs, so data-level assertions
        would become stale. Schema constraints are invariant after migration.
        """
        from cerebra.storage.db import connect
        from cerebra.storage.migrations import run_migrations

        run_migrations(vault_db)

        conn = connect(vault_db)
        try:
            rows = conn.execute("PRAGMA table_info(memory_records)").fetchall()
        finally:
            conn.close()

        col_info = {r[1]: {"notnull": r[3], "dflt_value": r[4]} for r in rows}

        assert (
            col_info["is_lattice_member"]["dflt_value"] == "0"
        ), "is_lattice_member must default to 0 so pre-migration rows are non-lattice"
        assert col_info["is_lattice_member"]["notnull"] == 1, "is_lattice_member must be NOT NULL"
        assert (
            col_info["lattice_lineage_id"]["dflt_value"] is None
        ), "lattice_lineage_id should have no default (NULL for non-members)"
        assert (
            col_info["lattice_confidence"]["dflt_value"] is None
        ), "lattice_confidence should have no default (NULL for non-members)"
