"""Unit tests for Migration014_Sessions — Phase 8 Step 1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cerebra.storage.migrations import ALL_MIGRATIONS, run_migrations


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "cerebra.db"
    p.touch()
    return p


class TestMigration014Schema:
    def test_runtime_sessions_table_created(self, db_path: Path) -> None:
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='runtime_sessions'"
        ).fetchone()
        assert row is not None, "runtime_sessions table not created"

    def test_required_columns_present(self, db_path: Path) -> None:
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(runtime_sessions)").fetchall()}
        required = {
            "session_id", "cycle_config", "goal", "vault_path",
            "opened_at", "parent_session_id", "recursion_depth",
            "max_recursion_depth", "cycles_run", "steps_run",
            "state", "flushed_at", "final_outcome",
        }
        for col in required:
            assert col in cols, f"Missing column: {col}"

    def test_primary_key_is_session_id(self, db_path: Path) -> None:
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        col_info = {
            r[1]: r for r in conn.execute("PRAGMA table_info(runtime_sessions)").fetchall()
        }
        # pk column is index 5 in PRAGMA table_info output
        assert col_info["session_id"][5] == 1, "session_id should be PRIMARY KEY"

    def test_indexes_created(self, db_path: Path) -> None:
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        indexes = {
            r[1]
            for r in conn.execute(
                "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='runtime_sessions'"
            ).fetchall()
        }
        expected = {
            "idx_runtime_sessions_parent",
            "idx_runtime_sessions_state",
            "idx_runtime_sessions_vault",
        }
        for idx in expected:
            assert idx in indexes, f"Missing index: {idx}"

    def test_migration_014_registered(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert 14 in versions, "Migration014_Sessions not registered in ALL_MIGRATIONS"

    def test_idempotent_double_run(self, db_path: Path) -> None:
        """Running migrations twice does not raise."""
        run_migrations(db_path)
        run_migrations(db_path)

    def test_default_values_in_schema(self, db_path: Path) -> None:
        """Inserting a minimal row sets state, cycles_run, steps_run, recursion_depth defaults."""
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO runtime_sessions (session_id, cycle_config, goal, vault_path, opened_at)
            VALUES ('sess_t1', 'default', 'test goal', '/tmp/v', 1700000000000)
            """
        )
        conn.commit()
        row = conn.execute(
            "SELECT state, cycles_run, steps_run, recursion_depth, max_recursion_depth "
            "FROM runtime_sessions WHERE session_id = 'sess_t1'"
        ).fetchone()
        state, cycles_run, steps_run, recursion_depth, max_recursion_depth = row
        assert state == "active"
        assert cycles_run == 0
        assert steps_run == 0
        assert recursion_depth == 0
        assert max_recursion_depth == 5

    def test_self_referential_fk_enforced(self, db_path: Path) -> None:
        """Parent session must exist before child can reference it."""
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO runtime_sessions (session_id, cycle_config, goal, vault_path, opened_at, parent_session_id)
                VALUES ('sess_child', 'default', 'g', '/tmp', 1700000000000, 'sess_nonexistent')
                """
            )
            conn.commit()

    def test_self_referential_fk_valid_parent(self, db_path: Path) -> None:
        """Parent exists → child insert succeeds."""
        run_migrations(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO runtime_sessions (session_id, cycle_config, goal, vault_path, opened_at) "
            "VALUES ('sess_parent', 'default', 'g', '/tmp', 1700000000000)"
        )
        conn.execute(
            "INSERT INTO runtime_sessions (session_id, cycle_config, goal, vault_path, opened_at, parent_session_id) "
            "VALUES ('sess_child', 'default', 'g', '/tmp', 1700000001000, 'sess_parent')"
        )
        conn.commit()
        row = conn.execute(
            "SELECT parent_session_id FROM runtime_sessions WHERE session_id='sess_child'"
        ).fetchone()
        assert row[0] == "sess_parent"
