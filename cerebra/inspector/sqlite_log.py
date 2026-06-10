"""
Inspector SQLite event log.

Writes events to the inspector_events table per CEREBRA_INSPECTOR.md §6.1.
The table is created by the Phase 0 migration; this module only writes/queries.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from cerebra.inspector.event import InspectorEvent
from cerebra.storage.db import connect


class SQLiteEventLog:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return connect(self._db_path)

    def write(self, event: InspectorEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO inspector_events (
                    event_id, event_type, schema_version, timestamp,
                    session_id, cycle_id, step_id, subject_id,
                    actor, summary, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.schema_version,
                    event.timestamp,
                    event.session_id,
                    event.cycle_id,
                    event.step_id,
                    event.subject_id,
                    event.actor,
                    event.summary,
                    json.dumps(event.data),
                ),
            )

    def query_by_type(self, event_type: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inspector_events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def query_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inspector_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def query_by_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM inspector_events WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def query_by_subject(
        self,
        subject_id: str,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return events for a subject_id, optionally filtered by event_type."""
        with self._connect() as conn:
            if event_type is not None:
                rows = conn.execute(
                    "SELECT * FROM inspector_events "
                    "WHERE subject_id = ? AND event_type = ? ORDER BY timestamp ASC",
                    (subject_id, event_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inspector_events "
                    "WHERE subject_id = ? ORDER BY timestamp ASC",
                    (subject_id,),
                ).fetchall()
        return [dict(row) for row in rows]
