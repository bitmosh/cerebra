"""
Forward-only SQLite migration framework.

Each migration is a versioned class that applies one schema change.
Migrations run idempotently: the applied_migrations table tracks what's been run.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from cerebra.storage.db import connect


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


class Migration002_Phase1Schema(Migration):
    """Phase 1: source memory foundation tables.

    One migration per phase discipline: sources, documents, chunks,
    and memory_records all land together here.

    NOTE on source identity: source_id is derived from canonical_path hash.
    A rename creates a new source; the old one goes stale. This is a known
    limitation — path-rename tracking is a Phase 3+ concern.
    """

    version = 2
    description = "Phase 1 source memory: sources, documents, chunks, memory_records"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                source_id           TEXT    PRIMARY KEY,
                canonical_path      TEXT    NOT NULL UNIQUE,
                content_hash        TEXT    NOT NULL,
                size_bytes          INTEGER NOT NULL,
                detected_type       TEXT    NOT NULL,
                detection_confidence REAL   NOT NULL,
                parser_adapter      TEXT,
                parser_version      TEXT,
                chunker_version     TEXT,
                parser_status       TEXT    NOT NULL DEFAULT 'pending',
                lifecycle_state     TEXT    NOT NULL DEFAULT 'active',
                created_at          INTEGER NOT NULL,
                modified_at         INTEGER,
                ingested_at         INTEGER,
                schema_version      INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_sources_path
                ON sources(canonical_path);
            CREATE INDEX IF NOT EXISTS idx_sources_hash
                ON sources(content_hash);
            CREATE INDEX IF NOT EXISTS idx_sources_state
                ON sources(lifecycle_state);

            CREATE TABLE IF NOT EXISTS documents (
                document_id             TEXT    PRIMARY KEY,
                source_id               TEXT    NOT NULL REFERENCES sources(source_id),
                document_type           TEXT    NOT NULL,
                title                   TEXT,
                artifact_path           TEXT,
                normalization_confidence REAL   NOT NULL DEFAULT 1.0,
                parse_warnings_json     TEXT,
                lifecycle_state         TEXT    NOT NULL DEFAULT 'active',
                created_at              INTEGER NOT NULL,
                schema_version          INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_documents_source
                ON documents(source_id);
            CREATE INDEX IF NOT EXISTS idx_documents_state
                ON documents(lifecycle_state);

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id        TEXT    PRIMARY KEY,
                document_id     TEXT    NOT NULL REFERENCES documents(document_id),
                source_id       TEXT    NOT NULL REFERENCES sources(source_id),
                heading_path    TEXT    NOT NULL DEFAULT '',
                chunk_index     INTEGER NOT NULL,
                depth           INTEGER NOT NULL DEFAULT 0,
                content         TEXT    NOT NULL,
                content_hash    TEXT    NOT NULL,
                token_estimate  INTEGER NOT NULL,
                chunk_strategy  TEXT    NOT NULL,
                lifecycle_state TEXT    NOT NULL DEFAULT 'active',
                created_at      INTEGER NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document
                ON chunks(document_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_source
                ON chunks(source_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_state
                ON chunks(lifecycle_state);

            CREATE TABLE IF NOT EXISTS memory_records (
                record_id       TEXT    PRIMARY KEY,
                record_type     TEXT    NOT NULL DEFAULT 'source_chunk',
                source_id       TEXT    NOT NULL REFERENCES sources(source_id),
                document_id     TEXT    NOT NULL REFERENCES documents(document_id),
                chunk_id        TEXT    NOT NULL REFERENCES chunks(chunk_id),
                content         TEXT    NOT NULL,
                content_hash    TEXT    NOT NULL,
                token_estimate  INTEGER NOT NULL,
                sku_address     TEXT,
                sku_assigned_at INTEGER,
                lifecycle_state TEXT    NOT NULL DEFAULT 'active',
                created_at      INTEGER NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_records_chunk
                ON memory_records(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_records_source
                ON memory_records(source_id);
            CREATE INDEX IF NOT EXISTS idx_records_sku
                ON memory_records(sku_address);
            CREATE INDEX IF NOT EXISTS idx_records_state
                ON memory_records(lifecycle_state);
        """)


# Registry: all migrations in ascending version order.
ALL_MIGRATIONS: list[Migration] = [
    Migration001_InitSchema(),
    Migration002_Phase1Schema(),
]


def run_migrations(db_path: Path) -> list[int]:
    """
    Apply all pending migrations to the database at db_path.
    Returns list of version numbers that were applied this run.
    """
    import time

    conn = connect(db_path)
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
