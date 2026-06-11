"""
Working memory — session management functions (Phase 5 Step 2).

WorkingMemory class and item-level operations are added in Step 3.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cerebra.inspector.event import make_event
from cerebra.storage.db import connect

if TYPE_CHECKING:
    from cerebra.inspector.sqlite_log import SQLiteEventLog


def _new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def new_session(
    db_path: Path,
    vault_path: str,
    event_log: SQLiteEventLog | None = None,
) -> str:
    """Create a new active session for vault_path.

    Any existing active session for the same vault is closed first — at most
    one active session per vault is the Phase 5 invariant (§2 D1).
    """
    now = int(time.time())
    conn = connect(db_path)
    try:
        existing = conn.execute(
            "SELECT session_id FROM sessions "
            "WHERE vault_path = ? AND status = 'active' "
            "ORDER BY started_at DESC LIMIT 1",
            (vault_path,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE sessions SET status = 'closed', last_active_at = ? "
                "WHERE session_id = ?",
                (now, existing["session_id"]),
            )

        session_id = _new_session_id()
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, vault_path, status, started_at, last_active_at, schema_version) "
            "VALUES (?, ?, 'active', ?, ?, 1)",
            (session_id, vault_path, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    if event_log is not None:
        event_log.write(
            make_event(
                event_type="WorkingMemoryCreated",
                actor="session",
                summary=f"Session created: {session_id}",
                data={
                    "session_id": session_id,
                    "vault_path": vault_path,
                    "started_at": now,
                },
                subject_id=session_id,
                session_id=session_id,
            )
        )

    return session_id


def get_active_session(db_path: Path, vault_path: str) -> str | None:
    """Return the active session_id for vault_path, or None if none exists."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT session_id FROM sessions "
            "WHERE vault_path = ? AND status = 'active' "
            "ORDER BY started_at DESC LIMIT 1",
            (vault_path,),
        ).fetchone()
    finally:
        conn.close()
    return row["session_id"] if row else None


def get_session_row(db_path: Path, session_id: str) -> dict[str, Any] | None:
    """Return the full session row as a dict, or None if not found."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT session_id, vault_path, status, started_at, last_active_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def close_session(db_path: Path, session_id: str) -> None:
    """Mark session as closed and update last_active_at."""
    now = int(time.time())
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE sessions SET status = 'closed', last_active_at = ? "
            "WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
    finally:
        conn.close()


def count_wm_items(db_path: Path, session_id: str) -> dict[str, int]:
    """Return {slot_type: count} for active working memory items in a session."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT slot_type, COUNT(*) AS n FROM working_memory_items "
            "WHERE session_id = ? AND evicted_at IS NULL "
            "GROUP BY slot_type",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    return {row["slot_type"]: row["n"] for row in rows}


def count_tower_items(db_path: Path, session_id: str) -> dict[int, int]:
    """Return {tier: count} for active tower items in a session."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT tier, COUNT(*) AS n FROM truth_tower_items "
            "WHERE session_id = ? AND evicted_at IS NULL "
            "GROUP BY tier",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    return {row["tier"]: row["n"] for row in rows}
