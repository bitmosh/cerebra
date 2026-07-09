# SPDX-License-Identifier: Apache-2.0
"""Phase 11 — LifecycleManager: memory_records lifecycle state machine.

Valid states:  active | archived | tombstoned
Valid transitions:
  active     → archived    (archive)
  active     → tombstoned  (tombstone)
  archived   → active      (restore)
  archived   → tombstoned  (tombstone)

Tombstoned is a terminal state — no transitions out. Restore only applies to
archived records.

Scope: memory_records only. cycle_episode_records is append-only session history
and is never lifecycle-managed. Lifecycle state on sources/documents/chunks is
managed by the ingest pipeline, not this module.

FTS5 sync: tombstone/archive removes the record from memory_records_fts;
restore re-adds it. This keeps the lexical index consistent without a full
rebuild after each transition.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from cerebra.inspector.event import make_event
from cerebra.inspector.sqlite_log import SQLiteEventLog
from cerebra.storage.db import connect
from cerebra.storage.lexical import FTS_TABLE

# ── State machine ─────────────────────────────────────────────────────────────

LIFECYCLE_STATES: frozenset[str] = frozenset({"active", "archived", "tombstoned"})

VALID_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("active", "archived"),
        ("active", "tombstoned"),
        ("archived", "active"),
        ("archived", "tombstoned"),
    }
)

# Human-readable operation names for error messages and events.
_TRANSITION_NAMES: dict[tuple[str, str], str] = {
    ("active", "archived"): "archive",
    ("active", "tombstoned"): "tombstone",
    ("archived", "active"): "restore",
    ("archived", "tombstoned"): "tombstone",
}


# ── Exceptions ────────────────────────────────────────────────────────────────


class LifecycleError(Exception):
    """Raised when a lifecycle transition is invalid or cannot be applied."""


class RecordNotFoundError(LifecycleError):
    """Raised when the target record_id does not exist in memory_records."""


class InvalidTransitionError(LifecycleError):
    """Raised when the requested transition is not permitted from the current state."""


# ── LifecycleManager ─────────────────────────────────────────────────────────


class LifecycleManager:
    """Applies lifecycle transitions to memory_records rows.

    Each transition:
    1. Validates the target state is reachable from the current state.
    2. Updates memory_records.lifecycle_state in a single atomic write.
    3. Syncs the FTS5 lexical index (delete on tombstone/archive, insert on restore).
    4. Emits an inspector event via event_log (if provided).
    """

    def __init__(self, db_path: Path, event_log: SQLiteEventLog | None = None) -> None:
        self.db_path = db_path
        self.event_log = event_log

    def transition(
        self,
        record_id: str,
        target_state: str,
        *,
        actor: str = "cli",
        reason: str | None = None,
    ) -> str:
        """Transition record_id to target_state. Returns the previous state."""
        if target_state not in LIFECYCLE_STATES:
            raise LifecycleError(f"Unknown lifecycle state: {target_state!r}")

        now = int(time.time() * 1000)

        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT rowid, lifecycle_state, record_type FROM memory_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()

            if row is None:
                raise RecordNotFoundError(f"record_id {record_id!r} not found in memory_records")

            rowid: int = row["rowid"]
            current_state: str = row["lifecycle_state"]
            record_type: str = row["record_type"]

            if current_state == target_state:
                return current_state

            if (current_state, target_state) not in VALID_TRANSITIONS:
                raise InvalidTransitionError(
                    f"Cannot transition {record_id!r} from {current_state!r} to {target_state!r}. "
                    f"Valid transitions from {current_state!r}: "
                    + ", ".join(t[1] for t in VALID_TRANSITIONS if t[0] == current_state)
                    or "none (terminal state)"
                )

            # Apply state change.
            conn.execute(
                "UPDATE memory_records SET lifecycle_state = ? WHERE record_id = ?",
                (target_state, record_id),
            )

            # Sync FTS5.
            _sync_fts(conn, rowid, record_id, current_state, target_state)

        # Emit inspector event.
        if self.event_log is not None:
            op = _TRANSITION_NAMES[(current_state, target_state)]
            event_type = _event_type_for_op(op)
            self.event_log.write(
                make_event(
                    event_type=event_type,
                    actor=actor,
                    summary=(
                        f"{op}: {record_id} ({current_state} → {target_state})"
                        + (f" reason={reason!r}" if reason else "")
                    ),
                    data={
                        "record_id": record_id,
                        "record_type": record_type,
                        "previous_state": current_state,
                        "new_state": target_state,
                        "actor": actor,
                        "reason": reason,
                        "transitioned_at": now,
                    },
                    subject_id=record_id,
                )
            )

        return current_state

    def batch_transition(
        self,
        record_ids: list[str],
        target_state: str,
        *,
        actor: str = "cli",
        reason: str | None = None,
    ) -> dict[str, str]:
        """Transition multiple records. Returns {record_id: previous_state} for successes.

        Failures are re-raised immediately (no partial-success semantics).
        """
        results: dict[str, str] = {}
        for record_id in record_ids:
            results[record_id] = self.transition(
                record_id, target_state, actor=actor, reason=reason
            )
        return results

    # ── Convenience methods ───────────────────────────────────────────────────

    def archive(self, record_id: str, *, actor: str = "cli", reason: str | None = None) -> str:
        return self.transition(record_id, "archived", actor=actor, reason=reason)

    def tombstone(self, record_id: str, *, actor: str = "cli", reason: str | None = None) -> str:
        return self.transition(record_id, "tombstoned", actor=actor, reason=reason)

    def restore(self, record_id: str, *, actor: str = "cli", reason: str | None = None) -> str:
        return self.transition(record_id, "active", actor=actor, reason=reason)

    def get_state(self, record_id: str) -> str | None:
        """Return the current lifecycle_state for record_id, or None if not found."""
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT lifecycle_state FROM memory_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        return row["lifecycle_state"] if row else None


# ── FTS5 sync helpers ─────────────────────────────────────────────────────────


def _fts_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (FTS_TABLE,),
    ).fetchone()
    return row is not None


def _sync_fts(
    conn: sqlite3.Connection,
    rowid: int,
    record_id: str,
    current_state: str,
    target_state: str,
) -> None:
    """Sync the FTS5 index entry for this record after a lifecycle transition.

    active → archived/tombstoned: delete from FTS.
    archived → active (restore):  re-insert into FTS.
    archived → tombstoned:        already absent from FTS (was active→archived earlier),
                                  nothing to do.
    """
    if not _fts_table_exists(conn):
        return

    is_leaving_active = current_state == "active" and target_state in ("archived", "tombstoned")
    is_restoring = current_state == "archived" and target_state == "active"

    if is_leaving_active:
        # FTS5 external content delete: must supply the same content that was indexed.
        content_row = conn.execute(
            "SELECT content FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if content_row is not None:
            conn.execute(
                f"INSERT INTO {FTS_TABLE}({FTS_TABLE}, rowid, content) VALUES('delete', ?, ?)",
                (rowid, content_row["content"]),
            )

    elif is_restoring:
        # Re-add to FTS.
        content_row = conn.execute(
            "SELECT content FROM memory_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if content_row is not None:
            conn.execute(
                f"INSERT INTO {FTS_TABLE}(rowid, content) VALUES(?, ?)",
                (rowid, content_row["content"]),
            )


# ── Event type mapping ────────────────────────────────────────────────────────


def _event_type_for_op(op: str) -> str:
    return {
        "archive": "MemoryRecordArchived",
        "tombstone": "MemoryRecordTombstoned",
        "restore": "MemoryRecordRestored",
    }[op]
