"""
Truth Tower — two-tier evidence stack (Phase 5).

T1: source-grounded evidence auto-populated from retrieval results.
T2: high-salience working memory items promoted manually, each citing a T1 anchor.

Both tiers share truth_tower_items (Migration009). Staleness is per-item:
when a T1 is evicted, all active T2 items that cite it are marked is_stale=1.
Stale T2s remain visible but are never auto-evicted.

WAL safety rule: all inspector event writes happen AFTER conn.close(). Writes
inside open transactions cause "database is locked" under WAL concurrency.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cerebra.cognition._constants import TOWER_CAPACITIES
from cerebra.inspector.event import make_event
from cerebra.storage.db import connect

if TYPE_CHECKING:
    from cerebra.cognition.working_memory import WorkingMemoryItem
    from cerebra.inspector.sqlite_log import SQLiteEventLog
    from cerebra.retrieval.context_packet import MemoryItem


class TowerPromotionError(Exception):
    """Raised when a tower promotion cannot be completed."""


@dataclass
class TowerItem:
    """A single item in the truth tower (T1 or T2)."""

    tower_item_id: str
    session_id: str
    tier: int
    wm_item_id: str | None
    record_id: str | None
    retrieval_trace_id: str | None
    content_summary: str
    salience_score: float
    sku_address: str | None
    t1_citation_id: str | None
    is_pinned: bool
    is_stale: bool
    promoted_at: int
    evicted_at: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tower_item_id": self.tower_item_id,
            "session_id": self.session_id,
            "tier": self.tier,
            "wm_item_id": self.wm_item_id,
            "record_id": self.record_id,
            "retrieval_trace_id": self.retrieval_trace_id,
            "content_summary": self.content_summary,
            "salience_score": self.salience_score,
            "sku_address": self.sku_address,
            "t1_citation_id": self.t1_citation_id,
            "is_pinned": self.is_pinned,
            "is_stale": self.is_stale,
            "promoted_at": self.promoted_at,
            "evicted_at": self.evicted_at,
        }


class TruthTower:
    """Two-tier evidence stack for a single session."""

    def __init__(self, db_path: Path, session_id: str) -> None:
        self.db_path = db_path
        self.session_id = session_id

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> TowerItem:
        return TowerItem(
            tower_item_id=row["tower_item_id"],
            session_id=row["session_id"],
            tier=row["tier"],
            wm_item_id=row["wm_item_id"],
            record_id=row["record_id"],
            retrieval_trace_id=row["retrieval_trace_id"],
            content_summary=row["content_summary"],
            salience_score=row["salience_score"],
            sku_address=row["sku_address"],
            t1_citation_id=row["t1_citation_id"],
            is_pinned=bool(row["is_pinned"]),
            is_stale=bool(row["is_stale"]),
            promoted_at=row["promoted_at"],
            evicted_at=row["evicted_at"],
        )

    def _load_tier_conn(self, conn: sqlite3.Connection, tier: int) -> list[TowerItem]:
        rows = conn.execute(
            "SELECT * FROM truth_tower_items "
            "WHERE session_id = ? AND tier = ? AND evicted_at IS NULL "
            "ORDER BY promoted_at ASC",
            (self.session_id, tier),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def _count_tier_conn(self, conn: sqlite3.Connection, tier: int) -> int:
        row = conn.execute(
            "SELECT COUNT(*) FROM truth_tower_items "
            "WHERE session_id = ? AND tier = ? AND evicted_at IS NULL",
            (self.session_id, tier),
        ).fetchone()
        return row[0] if row else 0

    def _is_first_t1_ever(self, conn: sqlite3.Connection) -> bool:
        """True if no T1 items of any state have ever been promoted in this session."""
        row = conn.execute(
            "SELECT COUNT(*) FROM truth_tower_items WHERE session_id = ? AND tier = 1",
            (self.session_id,),
        ).fetchone()
        return (row[0] if row else 0) == 0

    def _is_record_in_active_t1(self, conn: sqlite3.Connection, record_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM truth_tower_items "
            "WHERE session_id = ? AND record_id = ? AND tier = 1 AND evicted_at IS NULL LIMIT 1",
            (self.session_id, record_id),
        ).fetchone()
        return row is not None

    def _get_active_t1_chunk_ids(self, conn: sqlite3.Connection) -> set[str]:
        """Return chunk_ids held by active T1 items (for lattice sibling dedup)."""
        rows = conn.execute(
            "SELECT mr.chunk_id "
            "FROM truth_tower_items tti "
            "JOIN memory_records mr ON tti.record_id = mr.record_id "
            "WHERE tti.session_id = ? AND tti.tier = 1 AND tti.evicted_at IS NULL",
            (self.session_id,),
        ).fetchall()
        return {r["chunk_id"] for r in rows}

    def _evict_one_t1(
        self, conn: sqlite3.Connection, now: int
    ) -> tuple[str, float, int] | None:
        """
        Evict the lowest-salience non-pinned T1 item.
        Returns (tower_item_id, salience_score, pending_stale_count) or None if all pinned.
        The stale count is pre-computed but staling itself happens after conn.close().
        """
        candidates = [i for i in self._load_tier_conn(conn, 1) if not i.is_pinned]
        if not candidates:
            return None
        to_evict = min(candidates, key=lambda i: (i.salience_score, i.promoted_at))
        pending_stale = conn.execute(
            "SELECT COUNT(*) FROM truth_tower_items "
            "WHERE t1_citation_id = ? AND evicted_at IS NULL AND tier = 2 AND is_stale = 0",
            (to_evict.tower_item_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = ? WHERE tower_item_id = ?",
            (now, to_evict.tower_item_id),
        )
        return to_evict.tower_item_id, to_evict.salience_score, pending_stale

    def _evict_one_t2(
        self, conn: sqlite3.Connection, now: int
    ) -> tuple[str, float] | None:
        """Evict the lowest-salience non-pinned T2 item. Returns (id, salience) or None."""
        candidates = [i for i in self._load_tier_conn(conn, 2) if not i.is_pinned]
        if not candidates:
            return None
        to_evict = min(candidates, key=lambda i: (i.salience_score, i.promoted_at))
        conn.execute(
            "UPDATE truth_tower_items SET evicted_at = ? WHERE tower_item_id = ?",
            (now, to_evict.tower_item_id),
        )
        return to_evict.tower_item_id, to_evict.salience_score

    # ── public interface ──────────────────────────────────────────────────────

    def promote_to_t1(
        self,
        memory_items: list[MemoryItem],
        trace_id: str,
        event_log: SQLiteEventLog | None = None,
    ) -> list[TowerItem]:
        """
        Promote MemoryItems from a retrieval result into T1.

        Idempotent by (session_id, record_id, tier=1, evicted_at IS NULL) — re-running
        cerebra context with the same query does not duplicate T1 items.

        Lattice sibling dedup: when multiple MemoryItems share the same chunk_id
        (same underlying chunk committed to multiple SKU positions), only the first
        one encountered is promoted; the rest are skipped. Lattice Step 2 will add
        "which sibling wins" decision logic; for now, order-of-encounter decides.

        Emits TowerInitialized once (only on very first T1 in this session),
        TowerItemEvicted per capacity eviction, TowerItemStaled per T2 staled by
        a T1 eviction, TowerItemPromoted per new item.
        """
        if not memory_items:
            return []

        now = int(time.time())
        t1_capacity = TOWER_CAPACITIES[1]

        # Captured for post-close event emission
        was_first_t1 = False
        t1_evictions: list[tuple[str, float, int]] = []  # (id, salience, stale_count)
        new_items: list[TowerItem] = []
        promotion_data: list[dict[str, Any]] = []

        conn = connect(self.db_path)
        try:
            was_first_t1 = self._is_first_t1_ever(conn)
            seen_chunk_ids = self._get_active_t1_chunk_ids(conn)

            for mi in memory_items:
                # Idempotency: skip if this record is already in active T1
                if self._is_record_in_active_t1(conn, mi.record_id):
                    seen_chunk_ids.add(mi.chunk_id)  # still mark chunk as occupied
                    continue

                # Lattice sibling dedup: first sibling per chunk_id wins
                if mi.chunk_id in seen_chunk_ids:
                    continue

                # Capacity: evict if needed
                if self._count_tier_conn(conn, 1) >= t1_capacity:
                    result = self._evict_one_t1(conn, now)
                    if result is None:
                        raise TowerPromotionError(
                            f"T1 at capacity ({t1_capacity}) and all items are pinned; "
                            f"cannot promote {mi.record_id!r}"
                        )
                    t1_evictions.append(result)

                tid = _new_tower_item_id()
                conn.execute(
                    "INSERT INTO truth_tower_items "
                    "(tower_item_id, session_id, tier, wm_item_id, record_id, "
                    " retrieval_trace_id, content_summary, salience_score, "
                    " sku_address, is_pinned, promoted_at, schema_version) "
                    "VALUES (?, ?, 1, NULL, ?, ?, ?, ?, ?, 0, ?, 1)",
                    (
                        tid, self.session_id, mi.record_id, trace_id,
                        mi.content_excerpt[:400], mi.score, mi.sku_address, now,
                    ),
                )
                seen_chunk_ids.add(mi.chunk_id)
                new_items.append(
                    TowerItem(
                        tower_item_id=tid,
                        session_id=self.session_id,
                        tier=1,
                        wm_item_id=None,
                        record_id=mi.record_id,
                        retrieval_trace_id=trace_id,
                        content_summary=mi.content_excerpt[:400],
                        salience_score=mi.score,
                        sku_address=mi.sku_address,
                        t1_citation_id=None,
                        is_pinned=False,
                        is_stale=False,
                        promoted_at=now,
                        evicted_at=None,
                    )
                )
                promotion_data.append({
                    "session_id": self.session_id,
                    "tower_item_id": tid,
                    "tier": 1,
                    "record_id": mi.record_id,
                    "salience_score": mi.score,
                    "t1_citation_id": None,
                    "retrieval_trace_id": trace_id,
                    "source": "context_auto",
                    "_tid": tid,
                })

            conn.commit()
        finally:
            conn.close()

        if not new_items:
            return []

        if event_log is not None:
            if was_first_t1:
                event_log.write(
                    make_event(
                        "TowerInitialized", "truth_tower",
                        f"TowerInitialized for session {self.session_id}",
                        {
                            "session_id": self.session_id,
                            "tier": 1,
                            "t1_capacity": TOWER_CAPACITIES[1],
                            "t2_capacity": TOWER_CAPACITIES[2],
                        },
                        session_id=self.session_id,
                        subject_id=self.session_id,
                    )
                )

            for evicted_id, evicted_sal, stale_count in t1_evictions:
                # Stale cascade first (T2 events), then eviction event (the cause)
                self.mark_stale_from_t1_eviction(evicted_id, event_log)
                event_log.write(
                    make_event(
                        "TowerItemEvicted", "truth_tower",
                        f"T1 evicted (capacity): {evicted_id}",
                        {
                            "session_id": self.session_id,
                            "tower_item_id": evicted_id,
                            "tier": 1,
                            "salience_score": evicted_sal,
                            "eviction_reason": "capacity",
                            "stale_t2_count": stale_count,
                        },
                        session_id=self.session_id,
                        subject_id=evicted_id,
                    )
                )

            for pdata in promotion_data:
                tid = str(pdata.pop("_tid"))
                event_log.write(
                    make_event(
                        "TowerItemPromoted", "truth_tower",
                        f"T1 promoted: {pdata['record_id']} (score={pdata['salience_score']:.3f})",
                        pdata,
                        session_id=self.session_id,
                        subject_id=tid,
                    )
                )

        return new_items

    def promote_to_t2(
        self,
        wm_item: WorkingMemoryItem,
        t1_citation_id: str,
        is_pinned: bool = False,
        event_log: SQLiteEventLog | None = None,
    ) -> TowerItem:
        """
        Promote a working memory item to T2, citing a T1 anchor.

        Raises TowerPromotionError if:
        - Cited T1 does not exist in this session
        - Cited T1 is in a different session
        - Cited T1 is tier=2 (must cite a T1, not another T2)
        - Cited T1 has evicted_at IS NOT NULL (born-stale rejection, Amendment 4)
        - T2 at capacity and all existing T2 items are pinned
        """
        now = int(time.time())
        t2_capacity = TOWER_CAPACITIES[2]
        tid = ""
        salience = wm_item.salience_score
        capacity_eviction: tuple[str, float] | None = None

        conn = connect(self.db_path)
        try:
            cited_row = conn.execute(
                "SELECT tower_item_id, session_id, tier, evicted_at "
                "FROM truth_tower_items WHERE tower_item_id = ?",
                (t1_citation_id,),
            ).fetchone()

            if cited_row is None:
                raise TowerPromotionError(
                    f"Cited T1 item {t1_citation_id!r} does not exist"
                )
            if cited_row["session_id"] != self.session_id:
                raise TowerPromotionError(
                    f"Cited item {t1_citation_id!r} belongs to session "
                    f"{cited_row['session_id']!r}, not {self.session_id!r}"
                )
            if cited_row["tier"] != 1:
                raise TowerPromotionError(
                    f"Cited item {t1_citation_id!r} is tier={cited_row['tier']}, not tier=1; "
                    "T2 must cite a T1 item"
                )
            if cited_row["evicted_at"] is not None:
                raise TowerPromotionError(
                    f"Cannot promote to T2: cited T1 item {t1_citation_id!r} was evicted at "
                    f"{cited_row['evicted_at']}. Promote a current T1 first."
                )

            if self._count_tier_conn(conn, 2) >= t2_capacity:
                result = self._evict_one_t2(conn, now)
                if result is None:
                    raise TowerPromotionError(
                        f"T2 at capacity ({t2_capacity}) and all items are pinned; "
                        f"cannot promote wm_item {wm_item.item_id!r}"
                    )
                capacity_eviction = result

            tid = _new_tower_item_id()
            conn.execute(
                "INSERT INTO truth_tower_items "
                "(tower_item_id, session_id, tier, wm_item_id, record_id, "
                " content_summary, salience_score, sku_address, "
                " t1_citation_id, is_pinned, promoted_at, schema_version) "
                "VALUES (?, ?, 2, ?, ?, ?, ?, NULL, ?, ?, ?, 1)",
                (
                    tid, self.session_id, wm_item.item_id, wm_item.record_id,
                    wm_item.content_summary[:400], salience,
                    t1_citation_id, int(is_pinned), now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        item = TowerItem(
            tower_item_id=tid,
            session_id=self.session_id,
            tier=2,
            wm_item_id=wm_item.item_id,
            record_id=wm_item.record_id,
            retrieval_trace_id=None,
            content_summary=wm_item.content_summary[:400],
            salience_score=salience,
            sku_address=None,
            t1_citation_id=t1_citation_id,
            is_pinned=is_pinned,
            is_stale=False,
            promoted_at=now,
            evicted_at=None,
        )

        if event_log is not None:
            if capacity_eviction is not None:
                ev_id, ev_sal = capacity_eviction
                event_log.write(
                    make_event(
                        "TowerItemEvicted", "truth_tower",
                        f"T2 evicted (capacity): {ev_id}",
                        {
                            "session_id": self.session_id,
                            "tower_item_id": ev_id,
                            "tier": 2,
                            "salience_score": ev_sal,
                            "eviction_reason": "capacity",
                            "stale_t2_count": 0,
                        },
                        session_id=self.session_id,
                        subject_id=ev_id,
                    )
                )
            event_log.write(
                make_event(
                    "TowerCrossReferenceAdded", "truth_tower",
                    f"T2 {tid} cites T1 {t1_citation_id}",
                    {
                        "session_id": self.session_id,
                        "higher_item_id": tid,
                        "higher_tier": 2,
                        "lower_item_id": t1_citation_id,
                        "lower_tier": 1,
                    },
                    session_id=self.session_id,
                    subject_id=tid,
                )
            )
            event_log.write(
                make_event(
                    "TowerItemPromoted", "truth_tower",
                    f"T2 promoted: {tid} citing T1 {t1_citation_id}",
                    {
                        "session_id": self.session_id,
                        "tower_item_id": tid,
                        "tier": 2,
                        "record_id": wm_item.record_id,
                        "salience_score": salience,
                        "t1_citation_id": t1_citation_id,
                        "retrieval_trace_id": None,
                        "source": "manual_promote",
                    },
                    session_id=self.session_id,
                    subject_id=tid,
                )
            )

        return item

    def evict(
        self,
        tower_item_id: str,
        reason: str,
        event_log: SQLiteEventLog | None = None,
    ) -> None:
        """
        Explicitly evict a tower item by ID. Raises ValueError if not found.
        If T1, propagates staleness to all active T2 items that cite it.
        """
        now = int(time.time())
        tier: int = 0
        salience: float = 0.0

        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT tower_item_id, tier, salience_score "
                "FROM truth_tower_items "
                "WHERE tower_item_id = ? AND session_id = ? AND evicted_at IS NULL",
                (tower_item_id, self.session_id),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"Tower item {tower_item_id!r} not found or already evicted "
                    f"in session {self.session_id!r}"
                )
            tier = row["tier"]
            salience = row["salience_score"]

            conn.execute(
                "UPDATE truth_tower_items SET evicted_at = ? WHERE tower_item_id = ?",
                (now, tower_item_id),
            )
            conn.commit()
        finally:
            conn.close()

        stale_count = 0
        if tier == 1:
            stale_count = self.mark_stale_from_t1_eviction(tower_item_id, event_log)

        if event_log is not None:
            event_log.write(
                make_event(
                    "TowerItemEvicted", "truth_tower",
                    f"T{tier} evicted ({reason}): {tower_item_id}",
                    {
                        "session_id": self.session_id,
                        "tower_item_id": tower_item_id,
                        "tier": tier,
                        "salience_score": salience,
                        "eviction_reason": reason,
                        "stale_t2_count": stale_count,
                    },
                    session_id=self.session_id,
                    subject_id=tower_item_id,
                )
            )

    def load_tier(self, tier: int) -> list[TowerItem]:
        """Return all active (evicted_at IS NULL) items for the given tier, oldest first."""
        conn = connect(self.db_path)
        try:
            return self._load_tier_conn(conn, tier)
        finally:
            conn.close()

    def mark_stale_from_t1_eviction(
        self,
        t1_item_id: str,
        event_log: SQLiteEventLog | None = None,
    ) -> int:
        """
        Mark all active, not-yet-stale T2 items citing t1_item_id as is_stale=1.
        Emits TowerItemStaled per item. Returns count of newly staled items.
        Idempotent: already-stale items are skipped and not re-emitted.
        """
        staled: list[dict[str, Any]] = []

        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT tower_item_id, salience_score FROM truth_tower_items "
                "WHERE t1_citation_id = ? AND evicted_at IS NULL "
                "AND tier = 2 AND is_stale = 0",
                (t1_item_id,),
            ).fetchall()

            for row in rows:
                conn.execute(
                    "UPDATE truth_tower_items SET is_stale = 1 WHERE tower_item_id = ?",
                    (row["tower_item_id"],),
                )
                staled.append(
                    {
                        "session_id": self.session_id,
                        "staled_item_id": row["tower_item_id"],
                        "tier": 2,
                        "stale_reason": "t1_evicted",
                        "evicted_t1_id": t1_item_id,
                    }
                )
            conn.commit()
        finally:
            conn.close()

        if event_log is not None:
            for data in staled:
                staled_id = str(data["staled_item_id"])
                event_log.write(
                    make_event(
                        "TowerItemStaled", "truth_tower",
                        f"T2 {staled_id} staled: T1 {t1_item_id} evicted",
                        data,
                        session_id=self.session_id,
                        subject_id=staled_id,
                    )
                )

        return len(staled)

    def render_chronological(
        self,
        event_log: SQLiteEventLog | None = None,
    ) -> str:
        """
        Render the tower chronologically: T1 oldest-first, each T2 immediately
        under the T1 it cites. Stale T2 items marked with [stale].
        Emits TowerRendered.
        """
        conn = connect(self.db_path)
        try:
            t1_rows = conn.execute(
                "SELECT tti.tower_item_id, tti.content_summary, tti.salience_score, "
                "       tti.retrieval_trace_id, "
                "       COALESCE(s.canonical_path, 'synthetic') AS source_path "
                "FROM truth_tower_items tti "
                "LEFT JOIN memory_records mr ON tti.record_id = mr.record_id "
                "LEFT JOIN sources s ON mr.source_id = s.source_id "
                "WHERE tti.session_id = ? AND tti.tier = 1 AND tti.evicted_at IS NULL "
                "ORDER BY tti.promoted_at ASC",
                (self.session_id,),
            ).fetchall()

            t2_rows = conn.execute(
                "SELECT tti.tower_item_id, tti.content_summary, tti.salience_score, "
                "       tti.t1_citation_id, tti.is_stale, "
                "       COALESCE(s.canonical_path, 'synthetic') AS source_path "
                "FROM truth_tower_items tti "
                "LEFT JOIN memory_records mr ON tti.record_id = mr.record_id "
                "LEFT JOIN sources s ON mr.source_id = s.source_id "
                "WHERE tti.session_id = ? AND tti.tier = 2 AND tti.evicted_at IS NULL "
                "ORDER BY tti.promoted_at ASC",
                (self.session_id,),
            ).fetchall()
        finally:
            conn.close()

        t2_by_t1: dict[str, list[Any]] = {}
        for r in t2_rows:
            t2_by_t1.setdefault(r["t1_citation_id"], []).append(r)

        lines: list[str] = []
        for t1_idx, t1 in enumerate(t1_rows, start=1):
            trace = t1["retrieval_trace_id"] or "n/a"
            lines.append(
                f"T1 [{t1_idx}] {t1['source_path']}  "
                f"| score: {t1['salience_score']:.2f} | trace: {trace}"
            )
            lines.append(f"       {t1['content_summary'][:120]}")

            for t2_idx, t2 in enumerate(
                t2_by_t1.get(t1["tower_item_id"], []), start=1
            ):
                stale = " [stale]" if t2["is_stale"] else ""
                lines.append(
                    f"  T2 [{t2_idx}] ^T1[{t1_idx}]  {t2['source_path']}  "
                    f"| score: {t2['salience_score']:.2f}{stale}"
                )
                lines.append(f"         {t2['content_summary'][:120]}")

        rendered = "\n".join(lines)
        t1_count = len(t1_rows)
        t2_count = len(t2_rows)
        stale_count = sum(1 for r in t2_rows if r["is_stale"])

        if event_log is not None:
            event_log.write(
                make_event(
                    "TowerRendered", "truth_tower",
                    f"Tower rendered: {t1_count} T1, {t2_count} T2 ({stale_count} stale)",
                    {
                        "session_id": self.session_id,
                        "t1_count": t1_count,
                        "t2_count": t2_count,
                        "stale_count": stale_count,
                        "render_format": "chronological",
                        "token_estimate": max(1, len(rendered) // 4),
                        "included_in_packet": False,
                    },
                    session_id=self.session_id,
                    subject_id=self.session_id,
                )
            )

        return rendered

    def to_tower_field(
        self,
        event_log: SQLiteEventLog | None = None,
    ) -> dict[str, Any] | None:
        """
        Return the tower as a dict for ContextPacket inclusion, or None if empty.
        Emits TowerRendered with included_in_packet=True.
        """
        t1_items = self.load_tier(1)
        t2_items = self.load_tier(2)

        if not t1_items and not t2_items:
            return None

        stale_count = sum(1 for i in t2_items if i.is_stale)
        token_estimate = max(
            1,
            sum(len(i.content_summary) for i in t1_items + t2_items) // 4,
        )

        if event_log is not None:
            event_log.write(
                make_event(
                    "TowerRendered", "truth_tower",
                    f"Tower field: {len(t1_items)} T1, {len(t2_items)} T2 ({stale_count} stale)",
                    {
                        "session_id": self.session_id,
                        "t1_count": len(t1_items),
                        "t2_count": len(t2_items),
                        "stale_count": stale_count,
                        "render_format": "chronological",
                        "token_estimate": token_estimate,
                        "included_in_packet": True,
                    },
                    session_id=self.session_id,
                    subject_id=self.session_id,
                )
            )

        return {
            "t1_items": [i.to_dict() for i in t1_items],
            "t2_items": [i.to_dict() for i in t2_items],
            "t1_count": len(t1_items),
            "t2_count": len(t2_items),
            "stale_count": stale_count,
        }


# ── module-level helpers ──────────────────────────────────────────────────────


def _new_tower_item_id() -> str:
    return f"tti_{uuid.uuid4().hex[:12]}"
