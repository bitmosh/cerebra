"""
Working memory — session management and item-level operations (Phase 5).
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cerebra.cognition._constants import (
    SLOT_CAPACITIES,
    SYNTHETIC_ITEM_DEFAULT_SALIENCE,
)
from cerebra.inspector.event import make_event
from cerebra.storage.db import connect

if TYPE_CHECKING:
    from cerebra.inspector.sqlite_log import SQLiteEventLog


class PromotionError(Exception):
    """Raised when a working memory promotion cannot be completed."""


@dataclass
class WorkingMemoryItem:
    """A single item occupying a working memory slot."""

    item_id: str
    session_id: str
    slot_type: str
    record_id: str | None
    content_summary: str
    salience_score: float
    is_pinned: bool
    promoted_at: int
    evicted_at: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "session_id": self.session_id,
            "slot_type": self.slot_type,
            "record_id": self.record_id,
            "content_summary": self.content_summary,
            "salience_score": self.salience_score,
            "is_pinned": self.is_pinned,
            "promoted_at": self.promoted_at,
            "evicted_at": self.evicted_at,
        }


class WorkingMemory:
    """Slot-structured working memory for a single session."""

    def __init__(self, db_path: Path, session_id: str) -> None:
        self.db_path = db_path
        self.session_id = session_id

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> WorkingMemoryItem:
        return WorkingMemoryItem(
            item_id=row["item_id"],
            session_id=row["session_id"],
            slot_type=row["slot_type"],
            record_id=row["record_id"],
            content_summary=row["content_summary"],
            salience_score=row["salience_score"],
            is_pinned=bool(row["is_pinned"]),
            promoted_at=row["promoted_at"],
            evicted_at=row["evicted_at"],
        )

    @staticmethod
    def _is_tower_cited(conn: sqlite3.Connection, item_id: str) -> bool:
        """Return True if any active T2 tower item cites this wm item."""
        row = conn.execute(
            "SELECT 1 FROM truth_tower_items "
            "WHERE wm_item_id = ? AND evicted_at IS NULL LIMIT 1",
            (item_id,),
        ).fetchone()
        return row is not None

    def _load_slot_conn(
        self, conn: sqlite3.Connection, slot_type: str
    ) -> list[WorkingMemoryItem]:
        rows = conn.execute(
            "SELECT item_id, session_id, slot_type, record_id, content_summary, "
            "       salience_score, is_pinned, promoted_at, evicted_at "
            "FROM working_memory_items "
            "WHERE session_id = ? AND slot_type = ? AND evicted_at IS NULL "
            "ORDER BY promoted_at ASC",
            (self.session_id, slot_type),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    # ── public interface ──────────────────────────────────────────────────────

    def promote(
        self,
        slot_type: str,
        record_id: str | None,
        content_summary: str,
        salience_score: float | None = None,
        is_pinned: bool = False,
        event_log: SQLiteEventLog | None = None,
        source: str = "manual_promote",
    ) -> WorkingMemoryItem:
        """Insert an item into a slot, evicting the lowest-salience item if needed.

        Raises PromotionError if the slot is at capacity and all existing items
        are pinned (no eviction candidate).
        """
        if slot_type not in SLOT_CAPACITIES:
            raise ValueError(f"Unknown slot_type: {slot_type!r}")

        capacity = SLOT_CAPACITIES[slot_type]

        if salience_score is None:
            salience_score = SYNTHETIC_ITEM_DEFAULT_SALIENCE

        now = int(time.time())
        item_id = _new_item_id()

        # Emit AttentionItemProposed before any DB write
        if event_log is not None:
            event_log.write(
                make_event(
                    event_type="AttentionItemProposed",
                    actor="working_memory",
                    summary=f"Proposed {slot_type} item {item_id}",
                    data={
                        "session_id": self.session_id,
                        "item_id": item_id,
                        "slot_type": slot_type,
                        "record_id": record_id,
                        "content_summary": content_summary[:200],
                        "salience_score": salience_score,
                        "source": source,
                    },
                    subject_id=item_id,
                    session_id=self.session_id,
                )
            )

        # Captured post-commit event data; all writes happen after conn.close()
        # to avoid WAL writer contention.
        evicted_item_id: str | None = None
        eviction_event_data: dict[str, Any] | None = None
        deferred: bool = False

        conn = connect(self.db_path)
        try:
            # Step 1: insert optimistically
            conn.execute(
                "INSERT INTO working_memory_items "
                "(item_id, session_id, slot_type, record_id, content_summary, "
                " salience_score, is_pinned, promoted_at, schema_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    item_id, self.session_id, slot_type, record_id,
                    content_summary, salience_score, int(is_pinned), now,
                ),
            )

            # Step 2: count active items in slot (sees our uncommitted insert)
            active = self._load_slot_conn(conn, slot_type)

            # Step 3: evict if over capacity
            if len(active) > capacity:
                candidates = [
                    i for i in active
                    if i.item_id != item_id and not i.is_pinned
                ]
                if not candidates:
                    # All existing spots are pinned — roll back, then defer
                    conn.execute(
                        "DELETE FROM working_memory_items WHERE item_id = ?",
                        (item_id,),
                    )
                    deferred = True
                else:
                    # Effective salience: +0.20 for tower-cited items (eviction-resistant)
                    def _eff(i: WorkingMemoryItem) -> tuple[float, int]:
                        bonus = 0.20 if self._is_tower_cited(conn, i.item_id) else 0.0
                        return (i.salience_score + bonus, i.promoted_at)

                    to_evict = min(candidates, key=_eff)
                    was_tower_cited = self._is_tower_cited(conn, to_evict.item_id)

                    conn.execute(
                        "UPDATE working_memory_items SET evicted_at = ? "
                        "WHERE item_id = ?",
                        (now, to_evict.item_id),
                    )
                    evicted_item_id = to_evict.item_id
                    eviction_event_data = {
                        "session_id": self.session_id,
                        "item_id": to_evict.item_id,
                        "slot_type": to_evict.slot_type,
                        "salience_score": to_evict.salience_score,
                        "eviction_reason": "capacity",
                        "was_tower_cited": was_tower_cited,
                        "_summary": (
                            f"Evicted (capacity) {to_evict.slot_type} item {to_evict.item_id}"
                        ),
                        "_subject_id": to_evict.item_id,
                    }

            conn.commit()
        finally:
            conn.close()

        # Step 4: emit all events now that the connection is closed
        if deferred:
            if event_log is not None:
                event_log.write(
                    make_event(
                        event_type="AttentionItemDeferred",
                        actor="working_memory",
                        summary=f"Deferred {slot_type} item — slot full of pinned items",
                        data={
                            "session_id": self.session_id,
                            "item_id": item_id,
                            "slot_type": slot_type,
                            "salience_score": salience_score,
                            "defer_reason": "slot_full_pinned",
                        },
                        subject_id=item_id,
                        session_id=self.session_id,
                    )
                )
            raise PromotionError(
                f"Cannot promote: all {capacity} item(s) in slot "
                f"{slot_type!r} are pinned"
            )

        if eviction_event_data is not None and event_log is not None:
            summary = str(eviction_event_data.pop("_summary"))
            subject_id = str(eviction_event_data.pop("_subject_id"))
            event_log.write(
                make_event(
                    event_type="AttentionItemEvicted",
                    actor="working_memory",
                    summary=summary,
                    data=eviction_event_data,
                    subject_id=subject_id,
                    session_id=self.session_id,
                )
            )

        # Step 5: emit promotion event
        if event_log is not None:
            event_log.write(
                make_event(
                    event_type="AttentionItemPromoted",
                    actor="working_memory",
                    summary=f"Promoted {slot_type} item {item_id}",
                    data={
                        "session_id": self.session_id,
                        "item_id": item_id,
                        "slot_type": slot_type,
                        "salience_score": salience_score,
                        "record_id": record_id,
                        "eviction_triggered": evicted_item_id is not None,
                        "evicted_item_id": evicted_item_id,
                    },
                    subject_id=item_id,
                    session_id=self.session_id,
                )
            )

        return WorkingMemoryItem(
            item_id=item_id,
            session_id=self.session_id,
            slot_type=slot_type,
            record_id=record_id,
            content_summary=content_summary,
            salience_score=salience_score,
            is_pinned=is_pinned,
            promoted_at=now,
            evicted_at=None,
        )

    def evict(
        self,
        item_id: str,
        reason: str,
        event_log: SQLiteEventLog | None = None,
    ) -> None:
        """Explicitly evict an item by item_id. Raises ValueError if not found."""
        now = int(time.time())
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT item_id, slot_type, salience_score "
                "FROM working_memory_items "
                "WHERE item_id = ? AND session_id = ? AND evicted_at IS NULL",
                (item_id, self.session_id),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"Item {item_id!r} not found or already evicted in session {self.session_id!r}"
                )

            was_tower_cited = self._is_tower_cited(conn, item_id)
            slot_type = row["slot_type"]
            sal = row["salience_score"]

            conn.execute(
                "UPDATE working_memory_items SET evicted_at = ? WHERE item_id = ?",
                (now, item_id),
            )
            conn.commit()
        finally:
            conn.close()

        if event_log is not None:
            event_log.write(
                make_event(
                    event_type="AttentionItemEvicted",
                    actor="working_memory",
                    summary=f"Evicted ({reason}) item {item_id}",
                    data={
                        "session_id": self.session_id,
                        "item_id": item_id,
                        "slot_type": slot_type,
                        "salience_score": sal,
                        "eviction_reason": reason,
                        "was_tower_cited": was_tower_cited,
                    },
                    subject_id=item_id,
                    session_id=self.session_id,
                )
            )

    def load_slot(self, slot_type: str) -> list[WorkingMemoryItem]:
        """Return active items for a single slot, ordered by promoted_at ASC."""
        conn = connect(self.db_path)
        try:
            return self._load_slot_conn(conn, slot_type)
        finally:
            conn.close()

    def load_all_active(self) -> dict[str, list[WorkingMemoryItem]]:
        """Return all active items keyed by slot type. All 10 slot keys present."""
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT item_id, session_id, slot_type, record_id, content_summary, "
                "       salience_score, is_pinned, promoted_at, evicted_at "
                "FROM working_memory_items "
                "WHERE session_id = ? AND evicted_at IS NULL "
                "ORDER BY slot_type, promoted_at ASC",
                (self.session_id,),
            ).fetchall()
        finally:
            conn.close()

        result: dict[str, list[WorkingMemoryItem]] = {s: [] for s in SLOT_CAPACITIES}
        for row in rows:
            result[row["slot_type"]].append(self._row_to_item(row))
        return result

    def render_text(self) -> str:
        """Render current working memory as human-readable text."""
        all_items = self.load_all_active()
        total = sum(len(v) for v in all_items.values())

        lines: list[str] = [f"Working Memory ({total} items)"]
        for slot_type, items in sorted(all_items.items()):
            if not items:
                continue
            cap = SLOT_CAPACITIES[slot_type]
            lines.append(f"\n[{slot_type}]  ({len(items)}/{cap})")
            for item in items:
                pin_mark = "  [pinned]" if item.is_pinned else ""
                summary = item.content_summary
                if len(summary) > 120:
                    summary = summary[:120] + "…"
                lines.append(
                    f"  {item.item_id}  score: {item.salience_score:.4f}{pin_mark}"
                )
                lines.append(f"    {summary}")

        if total == 0:
            lines.append("\n(empty)")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable representation of active working memory."""
        all_items = self.load_all_active()
        return {
            "session_id": self.session_id,
            "total_item_count": sum(len(v) for v in all_items.values()),
            "slots": {
                slot: [item.to_dict() for item in items]
                for slot, items in all_items.items()
            },
        }


def _new_item_id() -> str:
    return f"wmi_{uuid.uuid4().hex[:12]}"


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
