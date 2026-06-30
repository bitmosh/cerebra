"""Tests for Migration013 — predictions + outcomes tables."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cerebra.storage.migrations import ALL_MIGRATIONS, run_migrations


def _fresh_db() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


@pytest.mark.unit
class TestMigration013Registry:
    def test_migration013_in_all_migrations(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert 13 in versions

    def test_migration013_after_012(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert versions.index(13) > versions.index(12)


@pytest.mark.unit
class TestMigration013Schema:
    def test_predictions_table_created(self) -> None:
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
            assert "predictions" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_outcomes_table_created(self) -> None:
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
            assert "outcomes" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_predictions_columns(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)").fetchall()}
            expected = {
                "prediction_id",
                "session_id",
                "cycle_id",
                "step_id",
                "expected_composite_score",
                "expected_per_signal",
                "prediction_basis",
                "confidence",
                "made_at",
            }
            assert expected.issubset(cols), f"Missing columns: {expected - cols}"
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_outcomes_columns(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(outcomes)").fetchall()}
            expected = {
                "outcome_id",
                "prediction_id",
                "session_id",
                "cycle_id",
                "step_id",
                "actual_composite_score",
                "prediction_error",
                "error_classification",
                "per_signal_error",
                "recorded_at",
            }
            assert expected.issubset(cols), f"Missing columns: {expected - cols}"
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_indexes_created(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            indexes = {
                row[1]
                for row in conn.execute("SELECT * FROM sqlite_master WHERE type='index'").fetchall()
            }
            assert "idx_predictions_session" in indexes
            assert "idx_outcomes_session" in indexes
            assert "idx_outcomes_classification" in indexes
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_predictions_insert_and_query(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("""
                INSERT INTO predictions
                    (prediction_id, session_id, cycle_id, step_id,
                     expected_composite_score, expected_per_signal,
                     prediction_basis, confidence, made_at)
                VALUES
                    ('pred_001', 'sess_001', 'cycle_001', 'step_001',
                     0.65, '{}', 'static_baseline', 0.5, 1718000000000)
            """)
            conn.commit()
            row = conn.execute(
                "SELECT expected_composite_score FROM predictions WHERE prediction_id='pred_001'"
            ).fetchone()
            assert row is not None
            assert abs(row[0] - 0.65) < 1e-9
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_outcomes_insert_and_query(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("""
                INSERT INTO predictions
                    (prediction_id, session_id, cycle_id, step_id,
                     expected_composite_score, expected_per_signal,
                     prediction_basis, confidence, made_at)
                VALUES
                    ('pred_002', 'sess_001', 'cycle_001', 'step_001',
                     0.65, '{}', 'static_baseline', 0.5, 1718000000000)
            """)
            conn.execute("""
                INSERT INTO outcomes
                    (outcome_id, prediction_id, session_id, cycle_id, step_id,
                     actual_composite_score, prediction_error, error_classification,
                     per_signal_error, recorded_at)
                VALUES
                    ('outcome_001', 'pred_002', 'sess_001', 'cycle_001', 'step_001',
                     0.72, 0.07, 'noise', '{}', 1718000001000)
            """)
            conn.commit()
            row = conn.execute(
                "SELECT error_classification FROM outcomes WHERE outcome_id='outcome_001'"
            ).fetchone()
            assert row is not None
            assert row[0] == "noise"
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_outcomes_fk_constraint_enforced(self) -> None:
        """outcomes.prediction_id must reference a valid predictions row."""
        db = _fresh_db()
        try:
            run_migrations(db)
            from cerebra.storage.db import connect as cerebra_connect

            conn = cerebra_connect(db)  # uses PRAGMA foreign_keys=ON
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""
                    INSERT INTO outcomes
                        (outcome_id, prediction_id, session_id, cycle_id, step_id,
                         actual_composite_score, prediction_error, error_classification,
                         per_signal_error, recorded_at)
                    VALUES
                        ('outcome_bad', 'pred_nonexistent', 'sess', 'cycle', 'step',
                         0.72, 0.07, 'noise', '{}', 1718000001000)
                """)
                conn.commit()
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration013_is_idempotent(self) -> None:
        db = _fresh_db()
        try:
            run_migrations(db)
            applied = run_migrations(db)
            assert 13 not in applied
        finally:
            db.unlink(missing_ok=True)

    def test_applies_after_012(self) -> None:
        """Migration 013 lands after 012 (evaluations table must exist)."""
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
            assert "predictions" in tables
            assert "outcomes" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)
