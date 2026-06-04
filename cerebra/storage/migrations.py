"""
Forward-only SQLite migration framework.

Each migration is a versioned class that applies one schema change.
Migrations run idempotently: the applied_migrations table tracks what's been run.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path


class Migration(ABC):
    """Base class for all Cerebra migrations."""

    version: int  # must be unique; applied in ascending order
    description: str

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply this migration. Called exactly once per vault."""


class Migration001_InitSchema(Migration):
    """Phase 0: create inspector_events table and migration metadata."""

    version = 1
    description = "Phase 0 initial schema: inspector_events + migration tracking"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT    NOT NULL,
                applied_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS inspector_events (
                event_id       TEXT    PRIMARY KEY,
                event_type     TEXT    NOT NULL,
                schema_version INTEGER NOT NULL,
                timestamp      INTEGER NOT NULL,
                session_id     TEXT,
                cycle_id       TEXT,
                step_id        TEXT,
                subject_id     TEXT,
                actor          TEXT    NOT NULL,
                summary        TEXT    NOT NULL,
                data_json      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_session
                ON inspector_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_cycle
                ON inspector_events(cycle_id);
            CREATE INDEX IF NOT EXISTS idx_events_type_time
                ON inspector_events(event_type, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_subject
                ON inspector_events(subject_id);
            """)


# Registry: all migrations in ascending version order.
ALL_MIGRATIONS: list[Migration] = [
    Migration001_InitSchema(),
]


def run_migrations(db_path: Path) -> list[int]:
    """
    Apply all pending migrations to the database at db_path.
    Returns list of version numbers that were applied this run.
    """
    import time

    conn = sqlite3.connect(db_path)
    try:
        # Bootstrap: ensure applied_migrations table exists before any query
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applied_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT    NOT NULL,
                applied_at  INTEGER NOT NULL
            )
            """)
        conn.commit()

        applied = {
            row[0] for row in conn.execute("SELECT version FROM applied_migrations").fetchall()
        }

        newly_applied: list[int] = []
        for migration in ALL_MIGRATIONS:
            if migration.version in applied:
                continue
            migration.up(conn)
            conn.execute(
                "INSERT INTO applied_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.description, int(time.time())),
            )
            conn.commit()
            newly_applied.append(migration.version)

        return newly_applied
    finally:
        conn.close()
