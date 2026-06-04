"""Unit tests for the migration framework."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cerebra.storage.migrations import ALL_MIGRATIONS, run_migrations


@pytest.mark.unit
class TestMigrations:
    def _fresh_db(self) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            return Path(f.name)

    def test_migration_creates_inspector_events_table(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "inspector_events" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migration_creates_applied_migrations_table(self) -> None:
        db = self._fresh_db()
        try:
            run_migrations(db)
            conn = sqlite3.connect(db)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "applied_migrations" in tables
            conn.close()
        finally:
            db.unlink(missing_ok=True)

    def test_migrations_are_idempotent(self) -> None:
        db = self._fresh_db()
        try:
            first = run_migrations(db)
            second = run_migrations(db)
            assert len(first) > 0
            assert second == []  # nothing new applied
        finally:
            db.unlink(missing_ok=True)

    def test_returns_applied_version_numbers(self) -> None:
        db = self._fresh_db()
        try:
            applied = run_migrations(db)
            assert 1 in applied
        finally:
            db.unlink(missing_ok=True)

    def test_all_migrations_have_unique_versions(self) -> None:
        versions = [m.version for m in ALL_MIGRATIONS]
        assert len(versions) == len(set(versions))

    def test_all_migrations_have_descriptions(self) -> None:
        for m in ALL_MIGRATIONS:
            assert m.description, f"Migration {m.version} has no description"
