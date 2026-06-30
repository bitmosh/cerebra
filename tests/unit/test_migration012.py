"""Tests for Migration012 — evaluations table."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cerebra.storage.migrations import ALL_MIGRATIONS, run_migrations

# ── helpers ───────────────────────────────────────────────────────────────────


def _fresh_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMigration012Registry:
    def test_migration012_in_all_migrations(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert 12 in versions

    def test_migration012_after_011(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert versions.index(12) > versions.index(11)


@pytest.mark.unit
class TestMigration012Schema:
    def test_evaluations_table_created(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "evaluations" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_evaluations_columns(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(evaluations)").fetchall()
            }
            expected = {
                "evaluation_id", "session_id", "cycle_id", "step_id",
                "composite_score", "per_signal_scores", "weights_used",
                "composite_floor_violated", "confidence", "composed_at",
            }
            assert expected.issubset(cols), f"Missing columns: {expected - cols}"
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_evaluations_indexes_created(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            indexes = {
                row[1]
                for row in conn.execute(
                    "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='evaluations'"
                ).fetchall()
            }
            assert "idx_evaluations_session" in indexes
            assert "idx_evaluations_cycle" in indexes
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_evaluations_insert_and_query(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("""
                INSERT INTO evaluations
                    (evaluation_id, session_id, cycle_id, step_id,
                     composite_score, per_signal_scores, weights_used,
                     composite_floor_violated, confidence, composed_at)
                VALUES
                    ('eval_001', 'sess_001', 'cycle_001', 'step_001',
                     0.72, '{}', '{}', 0, 1.0, 1718000000000)
            """)
            conn.commit()
            row = conn.execute(
                "SELECT composite_score FROM evaluations WHERE evaluation_id='eval_001'"
            ).fetchone()
            assert row is not None
            assert abs(row[0] - 0.72) < 1e-9
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration012_is_idempotent(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            applied = run_migrations(db)
            assert 12 not in applied
        finally:
            db.unlink(missing_ok=True)

    def test_migration012_description_references_evaluations(self) -> None:
        """Migration012 owns the evaluations table; predictions/outcomes are in 013."""
        m012 = next(m for m in ALL_MIGRATIONS if m.version == 12)
        assert "evaluations" in m012.description.lower()
